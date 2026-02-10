"""
PostgreSQL storage implementation using json payloads per logical file.
Stores all logical JSON files inside a single table with partner_id + filename keys.

Bulletproof connection pool with self-healing:
- Health checks on acquire
- Exponential backoff + jitter for transient errors
- Automatic pool recreation on stale connections
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import random
import uuid
import math
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar

import asyncpg

from app.storage.base import BaseStorage
from app.observability.trace import get_correlation_id
from app.observability.structured_logs import log_structured_event

logger = logging.getLogger(__name__)

# Type variable for generic retry return type
T = TypeVar("T")

# Transient errors that warrant retry with backoff
# These are connection/timeout issues that may resolve on retry
TRANSIENT_ERRORS: Tuple[type, ...] = (
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.InterfaceError,
    asyncpg.PostgresConnectionError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
)
_corr_lock_drop_total = 0


def _retry_transient(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator: retry method on transient DB errors with exponential backoff + jitter."""

    @functools.wraps(func)
    async def wrapper(self: "PostgresStorage", *args: Any, **kwargs: Any) -> T:
        last_exc: Optional[Exception] = None
        for attempt in range(self._retry_max_attempts):
            try:
                result = await func(self, *args, **kwargs)
                if attempt > 0:
                    self._reset_circuit()
                return result
            except asyncio.CancelledError:
                raise
            except TRANSIENT_ERRORS as exc:
                last_exc = exc
                if attempt < self._retry_max_attempts - 1:
                    delay = self._retry_base_delay * (2 ** attempt) + random.uniform(0, self._retry_jitter)
                    logger.warning(
                        "[STORAGE] transient_retry context=%s attempt=%d/%d error=%s(%s) delay=%.2fs",
                        func.__name__, attempt + 1, self._retry_max_attempts,
                        type(exc).__name__, str(exc)[:80], delay,
                    )
                    try:
                        await self._recreate_pool()
                    except Exception:
                        pass
                    await asyncio.sleep(delay)
                else:
                    self._maybe_open_circuit(exc, context=func.__name__)
                    raise
        raise last_exc  # type: ignore[misc]

    return wrapper  # type: ignore[return-value]

# System garbage keys that should never be stored as user data
SYSTEM_GARBAGE_KEYS = frozenset({
    "STATUS", "WARNING", "RESTORE_FEE", "METADATA", "_META",
    "ERROR", "INFO", "DEBUG", "SYSTEM", "CONFIG",
})

# Metrics counters for garbage filtering
_garbage_filter_stats = {
    "total_filtered": 0,
    "files_cleaned": set(),
}


def _is_valid_user_key(key: str) -> bool:
    """Check if a key is a valid user ID (numeric string)."""
    if not isinstance(key, str):
        return False
    return key.isdigit() and int(key) > 0


def _validate_user_id(user_id: int, operation: str) -> bool:
    """Validate user_id is a positive integer."""
    if not isinstance(user_id, int):
        logger.error("INVALID_USER_ID operation=%s user_id=%s type=%s expected=int",
                    operation, user_id, type(user_id).__name__)
        return False
    if user_id <= 0:
        logger.error("INVALID_USER_ID operation=%s user_id=%s reason=non_positive",
                    operation, user_id)
        return False
    return True


def _safe_float(value, default: float = 0.0, field: str = "unknown") -> float:
    """Safely convert value to float with logging on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            logger.warning("SAFE_FLOAT_FAILED field=%s value=%s type=str", field, value[:50] if len(value) > 50 else value)
            return default
    if isinstance(value, dict):
        # Try to extract 'balance' or 'amount' from dict
        for key in ('balance', 'amount', 'value'):
            if key in value:
                return _safe_float(value[key], default, field=f"{field}.{key}")
    logger.warning("SAFE_FLOAT_FAILED field=%s value_type=%s", field, type(value).__name__)
    return default


def _filter_garbage_keys_storage(data: dict, filename: str) -> dict:
    """Filter out garbage system keys from data before saving to storage."""
    if not isinstance(data, dict):
        return data
    
    garbage_found = [k for k in data.keys() if k in SYSTEM_GARBAGE_KEYS]
    # Also filter non-digit keys in user data files
    user_data_files = {
        "user_balances.json", "user_languages.json", "gift_claimed.json",
        "daily_free_generations.json", "referral_free_bank.json", "admin_limits.json",
    }
    invalid_keys = []
    if filename in user_data_files:
        invalid_keys = [k for k in data.keys() if not _is_valid_user_key(k) and k not in SYSTEM_GARBAGE_KEYS]
    
    all_garbage = list(set(garbage_found + invalid_keys))
    
    if all_garbage:
        filtered = {k: v for k, v in data.items() if k not in SYSTEM_GARBAGE_KEYS and (filename not in user_data_files or _is_valid_user_key(k))}
        _garbage_filter_stats["total_filtered"] += len(all_garbage)
        _garbage_filter_stats["files_cleaned"].add(filename)
        logger.warning(
            "STORAGE_GARBAGE_FILTERED filename=%s removed_keys=%s invalid_user_keys=%s before=%d after=%d total_filtered=%d",
            filename, garbage_found, invalid_keys, len(data), len(filtered), _garbage_filter_stats["total_filtered"]
        )
        return filtered
    return data


class PostgresStorage(BaseStorage):
    """PostgreSQL-backed storage that mirrors JsonStorage semantics.
    
    Bulletproof connection pool with self-healing:
    - Health checks on connection init and acquire
    - Exponential backoff + jitter for transient errors
    - Automatic pool recreation on stale connections
    - Circuit breaker to prevent cascade failures
    """

    def __init__(self, dsn: str, partner_id: Optional[str] = None) -> None:
        self.dsn = self._prepare_dsn(dsn)
        self.partner_id = (partner_id or os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or "").strip()
        if not self.partner_id:
            raise ValueError("BOT_INSTANCE_ID is required for multi-tenant storage")
        
        # Pool configuration from ENV
        max_pool_env = os.getenv("DB_MAX_CONN") or os.getenv("DB_MAXCONN", "10")
        try:
            self._max_pool_size = max(2, int(max_pool_env))
        except ValueError:
            logger.warning("Invalid DB_MAX_CONN=%s, using default 10", max_pool_env)
            self._max_pool_size = 10
        self._min_pool_size = 2  # Keep warm connections
        
        # Timeouts
        self._command_timeout = int(os.getenv("DB_COMMAND_TIMEOUT", "25"))
        self._max_inactive_lifetime = int(os.getenv("DB_MAX_INACTIVE_LIFETIME", "90"))
        
        # Pool state (per event loop) - locks created lazily to avoid event loop binding issues
        self._pool: Optional[asyncpg.Pool] = None
        self._pool_locks: Dict[int, asyncio.Lock] = {}  # Per-loop locks
        self._schema_ready = False
        
        # Legacy compatibility
        self.max_pool_size = self._max_pool_size
        self._pools: Dict[int, asyncpg.Pool] = {}
        self._schema_ready_loops: set[int] = set()
        self._file_locks: Dict[Tuple[int, str], asyncio.Lock] = {}
        
        # Circuit breaker
        self._circuit_open_until = 0.0
        self._circuit_open_seconds = float(os.getenv("DB_CIRCUIT_OPEN_SECONDS", "5"))
        self._circuit_open_reason: Optional[str] = None
        self._consecutive_failures = 0
        self._max_consecutive_failures = int(os.getenv("DB_CIRCUIT_FAILURE_THRESHOLD", "3"))
        
        # Retry configuration
        self._retry_base_delay = 0.25
        self._retry_max_attempts = 4
        self._retry_jitter = 0.15

        # logical filenames (same as JsonStorage/GitHubStorage)
        self.balances_file = "user_balances.json"
        self.languages_file = "user_languages.json"
        self.gift_claimed_file = "gift_claimed.json"
        self.free_generations_file = "daily_free_generations.json"
        self.hourly_free_usage_file = "hourly_free_usage.json"
        self.referral_free_bank_file = "referral_free_bank.json"
        self.admin_limits_file = "admin_limits.json"
        self.generations_history_file = "generations_history.json"
        self.payments_file = "payments.json"
        self.referrals_file = "referrals.json"
        self.jobs_file = "generation_jobs.json"
        self.balance_deductions_file = "balance_deductions.json"
        self.free_deductions_file = "free_deductions.json"

    @staticmethod
    def _coerce_payload(payload: Any, *, filename: str) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        logger.warning("STORAGE_JSON_TYPE_INVALID filename=%s payload_type=%s", filename, type(payload).__name__)
        return {}

    @staticmethod
    def _prepare_dsn(dsn: str) -> str:
        """Prepare DSN for Render: add sslmode if missing."""
        if not dsn:
            return dsn
        # Render internal URLs don't need SSL, but external do
        # Add sslmode=prefer if not specified — works for both internal and external
        if "sslmode" not in dsn:
            separator = "&" if "?" in dsn else "?"
            dsn = f"{dsn}{separator}sslmode=prefer"
            logger.info("[STORAGE] dsn_prepared=true added_sslmode=prefer")
        # Log DSN info (mask password)
        try:
            import re
            masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', dsn)
            logger.info("[STORAGE] dsn_info=%s", masked)
        except Exception:
            pass
        return dsn

    async def _init_conn(self, conn: asyncpg.Connection) -> None:
        """Initialize connection with health check and session settings."""
        await conn.execute("SELECT 1")
        # Optional: set session-level timeouts
        # await conn.execute("SET statement_timeout = '30s'")
        # await conn.execute("SET idle_in_transaction_session_timeout = '60s'")

    def _get_pool_lock(self) -> asyncio.Lock:
        """Get or create pool lock for current event loop (avoids 'bound to different loop' errors)."""
        loop_id = id(asyncio.get_running_loop())
        lock = self._pool_locks.get(loop_id)
        if lock is None:
            lock = asyncio.Lock()
            self._pool_locks[loop_id] = lock
        return lock

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Get or create the connection pool with lazy initialization."""
        if self._is_circuit_open():
            raise RuntimeError(f"PostgresStorage circuit open: {self._circuit_open_reason or 'unknown'}")
        
        if self._pool is not None:
            return self._pool
        
        async with self._get_pool_lock():
            # Double-check after acquiring lock
            if self._pool is not None:
                return self._pool
            
            self._pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
                init=self._init_conn,
                command_timeout=self._command_timeout,
                max_inactive_connection_lifetime=self._max_inactive_lifetime,
            )
            self._reset_circuit()
            logger.info(
                "[STORAGE] pool_created=true min=%d max=%d timeout=%ds inactive_lifetime=%ds",
                self._min_pool_size, self._max_pool_size,
                self._command_timeout, self._max_inactive_lifetime,
            )
            
            # Ensure schema
            if not self._schema_ready:
                await self._ensure_schema_new(self._pool)
                self._schema_ready = True
            
            return self._pool

    async def _recreate_pool(self) -> asyncpg.Pool:
        """Close old pool and create a fresh one."""
        async with self._get_pool_lock():
            old_pool = self._pool
            self._pool = None
            self._schema_ready = False
            
            if old_pool is not None:
                try:
                    await asyncio.wait_for(old_pool.close(), timeout=5.0)
                    logger.info("[STORAGE] old_pool_closed=true")
                except RuntimeError as e:
                    # Pool was created on a different event loop — can't close, just discard
                    logger.info("[STORAGE] old_pool_discarded=true reason=%s", e)
                except Exception as e:
                    logger.warning("[STORAGE] old_pool_close_error=%s", e)
            
            return await self._ensure_pool()

    async def _with_retry(
        self,
        fn: Callable[[], Awaitable[T]],
        *,
        context: str = "db_op",
    ) -> T:
        """Execute fn with exponential backoff + jitter for transient errors."""
        last_exc: Optional[Exception] = None
        
        for attempt in range(self._retry_max_attempts):
            try:
                result = await fn()
                # Success - reset failure counter
                if self._consecutive_failures > 0:
                    self._reset_circuit()
                return result
            except asyncio.CancelledError:
                # Never retry on cancellation - propagate immediately
                raise
            except TRANSIENT_ERRORS as exc:
                last_exc = exc
                self._consecutive_failures += 1
                
                if attempt == self._retry_max_attempts - 1:
                    # Last attempt failed
                    logger.error(
                        "[STORAGE] retry_exhausted context=%s attempts=%d error=%s",
                        context, self._retry_max_attempts, exc,
                    )
                    self._maybe_open_circuit(exc, context=context)
                    raise
                
                # Calculate backoff with jitter
                delay = self._retry_base_delay * (2 ** attempt) + random.random() * self._retry_jitter
                logger.warning(
                    "[STORAGE] transient_retry context=%s attempt=%d/%d error=%s delay=%.2fs",
                    context, attempt + 1, self._retry_max_attempts, type(exc).__name__, delay,
                )
                
                # Recreate pool on connection errors
                if isinstance(exc, (asyncpg.ConnectionDoesNotExistError, asyncpg.InterfaceError, ConnectionError)):
                    try:
                        await self._recreate_pool()
                    except Exception as recreate_exc:
                        logger.warning("[STORAGE] pool_recreate_failed=%s", recreate_exc)
                
                await asyncio.sleep(delay)
            except Exception as exc:
                # Non-transient error - don't retry
                self._maybe_open_circuit(exc, context=context)
                raise
        
        # Should not reach here, but satisfy type checker
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Retry loop exited without result or exception")

    async def _acquire_healthy(self) -> asyncpg.connection.Connection:
        """Acquire a connection with health check, recreate pool on failure."""
        pool = await self._ensure_pool()
        conn = await pool.acquire()
        
        try:
            # Quick health check
            await conn.execute("SELECT 1")
            return conn
        except Exception as health_exc:
            # Connection is bad - release and recreate pool
            logger.warning("[STORAGE] health_check_failed=%s", health_exc)
            try:
                await pool.release(conn)
            except Exception:
                pass
            
            # Recreate pool and try again
            pool = await self._recreate_pool()
            conn = await pool.acquire()
            await conn.execute("SELECT 1")
            return conn

    async def _release_conn(self, conn: asyncpg.connection.Connection) -> None:
        """Safely release connection back to pool."""
        pool = self._pool
        if pool is not None:
            try:
                await pool.release(conn)
            except Exception as e:
                logger.warning("[STORAGE] release_conn_error=%s", e)

    async def _get_pool(self) -> asyncpg.Pool:
        """Legacy method for backward compatibility."""
        return await self._ensure_pool()

    async def _ensure_schema_new(self, pool: asyncpg.Pool) -> None:
        """Ensure database schema exists."""
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_json (
                    partner_id TEXT NOT NULL,
                    filename   TEXT NOT NULL,
                    payload    JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (partner_id, filename)
                );
                CREATE TABLE IF NOT EXISTS migrations_meta (
                    key TEXT PRIMARY KEY,
                    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS referrals (
                    partner_id TEXT NOT NULL,
                    referred_user_id BIGINT NOT NULL,
                    referrer_id BIGINT NOT NULL,
                    ref_param TEXT,
                    bonus_amount INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    bonus_granted_at TIMESTAMPTZ,
                    PRIMARY KEY (partner_id, referred_user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id
                    ON referrals(partner_id, referrer_id);
                CREATE INDEX IF NOT EXISTS idx_referrals_created_at
                    ON referrals(partner_id, created_at DESC);
                """
            )
        logger.info("[STORAGE] schema_ready=true partner_id=%s", self.partner_id)

    async def _ensure_schema(self, pool: asyncpg.Pool, loop_id: int) -> None:
        if loop_id in self._schema_ready_loops:
            return
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS storage_json (
                        partner_id TEXT NOT NULL,
                        filename   TEXT NOT NULL,
                        payload    JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (partner_id, filename)
                    );
                    CREATE TABLE IF NOT EXISTS migrations_meta (
                        key TEXT PRIMARY KEY,
                        completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE TABLE IF NOT EXISTS referrals (
                        partner_id TEXT NOT NULL,
                        referred_user_id BIGINT NOT NULL,
                        referrer_id BIGINT NOT NULL,
                        ref_param TEXT,
                        bonus_amount INTEGER,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        bonus_granted_at TIMESTAMPTZ,
                        PRIMARY KEY (partner_id, referred_user_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id
                        ON referrals(partner_id, referrer_id);
                    CREATE INDEX IF NOT EXISTS idx_referrals_created_at
                        ON referrals(partner_id, created_at DESC);
                    """
                )
        except Exception as exc:
            self._maybe_open_circuit(exc, context="ensure_schema")
            raise
        self._schema_ready_loops.add(loop_id)
        logger.info("[STORAGE] schema_ready=true partner_id=%s", self.partner_id)

    def _get_file_lock(self, filename: str) -> asyncio.Lock:
        loop_id = id(asyncio.get_running_loop())
        key = (loop_id, filename)
        lock = self._file_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._file_locks[key] = lock
        return lock

    def _is_circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_open_until

    def _open_circuit(self, reason: str) -> None:
        self._circuit_open_until = time.monotonic() + self._circuit_open_seconds
        self._circuit_open_reason = reason
        logger.warning(
            "[STORAGE] circuit_open=true reason=%s cooldown_s=%s",
            reason,
            self._circuit_open_seconds,
        )

    def _reset_circuit(self) -> None:
        """Reset circuit breaker after successful connection."""
        if self._circuit_open_reason or self._consecutive_failures > 0:
            logger.info("[STORAGE] circuit_reset=true previous_reason=%s failures=%d", 
                       self._circuit_open_reason, self._consecutive_failures)
        self._circuit_open_until = 0.0
        self._circuit_open_reason = None
        self._consecutive_failures = 0

    def _invalidate_pool(self) -> None:
        """Mark pool for recreation on next use. Do NOT close synchronously - causes race conditions."""
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if loop_id in self._pools:
            # Do NOT close pool here - just remove reference so new one is created
            # Closing causes ConnectionDoesNotExistError for in-flight requests
            self._pools.pop(loop_id, None)
            self._schema_ready_loops.discard(loop_id)
            logger.info("[STORAGE] pool_invalidated=true loop_id=%s (will recreate on next use)", loop_id)

    def _maybe_open_circuit(self, exc: Exception, *, context: str) -> None:
        if isinstance(
            exc,
            (
                asyncio.TimeoutError,
                TimeoutError,
                OSError,
                ConnectionError,
                asyncpg.PostgresError,
            ),
        ):
            self._consecutive_failures += 1
            logger.warning(
                "[STORAGE] db_failure context=%s error=%s(%s) consecutive=%d/%d",
                context, type(exc).__name__, str(exc)[:100],
                self._consecutive_failures, self._max_consecutive_failures,
            )
            # Only invalidate pool on explicit connection refused errors
            if isinstance(exc, ConnectionRefusedError):
                self._invalidate_pool()
            # Only open circuit after reaching threshold
            if self._consecutive_failures >= self._max_consecutive_failures:
                self._open_circuit(f"{context}:{exc.__class__.__name__}")
        else:
            # Non-connection errors (e.g. SQL errors) don't count toward circuit
            logger.debug("[STORAGE] non_circuit_error context=%s error=%s", context, type(exc).__name__)

    async def _load_json_unlocked(self, filename: str) -> Dict[str, Any]:
        """Load JSON data from storage with automatic retry on transient errors."""
        
        async def _do_load() -> Optional[asyncpg.Record]:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                return await conn.fetchrow(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    filename,
                )
        
        row = await self._with_retry(_do_load, context="load_json")
        
        # AUDIT: Log critical files
        if filename in ("user_registry.json", "payments.json", "user_balances.json"):
            if row:
                payload_preview = row[0]
                keys_count = len(payload_preview) if isinstance(payload_preview, dict) else 0
                sample_keys = list(payload_preview.keys())[:5] if isinstance(payload_preview, dict) else []
                logger.info("PG_LOAD_AUDIT file=%s partner_id=%s row_found=true keys=%d sample=%s", 
                           filename, self.partner_id, keys_count, sample_keys)
            else:
                logger.info("PG_LOAD_AUDIT file=%s partner_id=%s row_found=false", 
                           filename, self.partner_id)
        
        if not row:
            return {}
        
        return self._coerce_payload(row[0], filename=filename)

    async def _load_json(self, filename: str) -> Dict[str, Any]:
        lock = self._get_file_lock(filename)
        async with lock:
            return await self._load_json_unlocked(filename)

    async def _save_json_unlocked(self, filename: str, data: Dict[str, Any]) -> None:
        # Filter garbage keys before saving
        clean_data = _filter_garbage_keys_storage(data, filename)
        
        # ============================================================
        # CRITICAL DATA LOSS PROTECTION v3.0
        # Comprehensive protection + automatic backup
        # ============================================================
        CRITICAL_FILES = {"payments.json", "user_registry.json", "user_balances.json", "generations_history.json"}
        
        new_keys_count = len(clean_data) if isinstance(clean_data, dict) else 0
        current_data = {}
        current_keys_count = 0
        
        if filename in CRITICAL_FILES:
            # Load current data to compare AND backup
            try:
                current_data = await self._load_json_unlocked(filename)
                current_keys_count = len(current_data) if isinstance(current_data, dict) else 0
            except Exception:
                current_keys_count = 0
            
            # AUTO-BACKUP: Save backup before any write to critical files (if data exists)
            if current_keys_count > 0:
                backup_filename = f"_backup_{filename}"
                backup_json = json.dumps(current_data)
                
                async def _do_backup() -> None:
                    pool = await self._ensure_pool()
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO storage_json (partner_id, filename, payload)
                            VALUES ($1, $2, $3::jsonb)
                            ON CONFLICT (partner_id, filename)
                            DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                            """,
                            self.partner_id,
                            backup_filename,
                            backup_json,
                        )
                
                try:
                    await self._with_retry(_do_backup, context="auto_backup")
                    logger.info(
                        "AUTO_BACKUP_SAVED file=%s backup=%s keys=%d partner_id=%s",
                        filename, backup_filename, current_keys_count, self.partner_id
                    )
                except Exception as backup_exc:
                    logger.warning("AUTO_BACKUP_FAILED file=%s error=%s", filename, backup_exc)
            
            # BLOCK 1: Never overwrite non-empty data with empty data
            if current_keys_count > 0 and new_keys_count == 0:
                logger.error(
                    "CRITICAL_DATA_LOSS_BLOCKED file=%s current_keys=%d new_keys=%d "
                    "reason=REFUSING_TO_OVERWRITE_WITH_EMPTY partner_id=%s",
                    filename, current_keys_count, new_keys_count, self.partner_id
                )
                raise ValueError(
                    f"DATA_LOSS_PROTECTION: Refusing to overwrite {filename} "
                    f"(has {current_keys_count} records) with empty data!"
                )
            
            # BLOCK 2: Never create new empty critical files (except during legitimate init)
            if current_keys_count == 0 and new_keys_count == 0:
                import traceback
                stack = ''.join(traceback.format_stack())
                is_migration = 'migrate_from_github' in stack or 'migrate' in stack.lower()
                is_init = '_ensure_' in stack or 'initialize' in stack.lower()
                
                if is_migration:
                    logger.warning(
                        "MIGRATION_EMPTY_FILE_SKIPPED file=%s reason=source_was_empty partner_id=%s",
                        filename, self.partner_id
                    )
                    return  # Don't write empty file during migration
                elif not is_init:
                    logger.warning(
                        "EMPTY_CRITICAL_FILE_WRITE file=%s current=0 new=0 partner_id=%s",
                        filename, self.partner_id
                    )
            
            # BLOCK 3: Never reduce data by more than 80% in single operation
            if current_keys_count > 10 and new_keys_count < current_keys_count * 0.2:
                logger.error(
                    "CRITICAL_DATA_LOSS_BLOCKED file=%s current_keys=%d new_keys=%d "
                    "reason=EXCESSIVE_DATA_REDUCTION partner_id=%s",
                    filename, current_keys_count, new_keys_count, self.partner_id
                )
                raise ValueError(
                    f"DATA_LOSS_PROTECTION: Refusing to reduce {filename} by >80% "
                    f"({current_keys_count} → {new_keys_count} records)!"
                )
            
            # WARN: Significant data reduction (more than 50% loss)
            if current_keys_count > 5 and new_keys_count < current_keys_count * 0.5:
                logger.warning(
                    "CRITICAL_DATA_REDUCTION_WARNING file=%s current_keys=%d new_keys=%d "
                    "reduction_pct=%.1f%% partner_id=%s",
                    filename, current_keys_count, new_keys_count,
                    (1 - new_keys_count / current_keys_count) * 100,
                    self.partner_id
                )
            
            # Log all writes to critical files
            logger.info(
                "CRITICAL_FILE_WRITE file=%s current_keys=%d new_keys=%d partner_id=%s",
                filename, current_keys_count, new_keys_count, self.partner_id
            )
        
        # Save with automatic retry on transient errors
        payload_json = json.dumps(clean_data) if isinstance(clean_data, dict) else "{}"
        
        async def _do_save() -> None:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO storage_json (partner_id, filename, payload)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (partner_id, filename)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                    """,
                    self.partner_id,
                    filename,
                    payload_json,
                )
        
        await self._with_retry(_do_save, context="save_json")

    async def _save_json(self, filename: str, data: Dict[str, Any]) -> None:
        lock = self._get_file_lock(filename)
        async with lock:
            await self._save_json_unlocked(filename, data)

    async def _update_json(self, filename: str, update_fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        lock = self._get_file_lock(filename)
        async with lock:
            current = await self._load_json_unlocked(filename)
            updated = update_fn(dict(current))
            # Filter garbage keys after update function runs
            clean_updated = _filter_garbage_keys_storage(updated, filename)
            await self._save_json_unlocked(filename, clean_updated)
            return clean_updated

    def _advisory_lock_key_pair(self, filename: str):
        from app.utils.pg_advisory_lock import build_advisory_lock_key_pair

        payload = f"{self.partner_id}:{filename}"
        return build_advisory_lock_key_pair(source="storage_json", payload=payload)

    # ==================== USER OPERATIONS ====================

    async def get_user(self, user_id: int, upsert: bool = True) -> Dict[str, Any]:
        balance = await self.get_user_balance(user_id)
        language = await self.get_user_language(user_id)
        gift_claimed = await self.has_claimed_gift(user_id)
        referrer_id = await self.get_referrer(user_id)

        return {
            "user_id": user_id,
            "balance": balance,
            "language": language,
            "gift_claimed": gift_claimed,
            "referrer_id": referrer_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    async def get_user_balance(self, user_id: int) -> float:
        if not _validate_user_id(user_id, "get_user_balance"):
            return 0.0
        data = await self._load_json(self.balances_file)
        raw_value = data.get(str(user_id), 0.0)
        return _safe_float(raw_value, default=0.0, field=f"balance[{user_id}]")

    async def set_user_balance(self, user_id: int, amount: float) -> None:
        if not _validate_user_id(user_id, "set_user_balance"):
            logger.error("SET_BALANCE_REJECTED user_id=%s reason=invalid_user_id", user_id)
            return
        balance_before = await self.get_user_balance(user_id)
        data = await self._load_json(self.balances_file)
        data[str(user_id)] = amount
        await self._save_json(self.balances_file, data)
        logger.info(
            "BALANCE_SET user_id=%s balance_before=%.2f balance_after=%.2f delta=%.2f",
            user_id,
            balance_before,
            amount,
            amount - balance_before,
        )

    @_retry_transient
    async def add_user_balance(self, user_id: int, amount: float) -> float:
        """Add to user balance with transaction lock to prevent race conditions."""
        if not _validate_user_id(user_id, "add_user_balance"):
            logger.error("ADD_BALANCE_REJECTED user_id=%s amount=%.2f reason=invalid_user_id", user_id, amount)
            return 0.0
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Ensure file exists
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balances_file,
                )
                # Lock row and get current balance
                payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balances_file,
                )
                balances = self._coerce_payload(payload, filename=self.balances_file)
                # Filter garbage keys before processing
                balances = _filter_garbage_keys_storage(balances, self.balances_file)
                balance_before = _safe_float(balances.get(str(user_id), 0.0), field=f"balance[{user_id}]")
                new_balance = balance_before + amount
                balances[str(user_id)] = new_balance
                
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balances_file,
                    json.dumps(balances),
                )
        logger.info(
            "BALANCE_ADD user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return new_balance

    @_retry_transient
    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        """Subtract from user balance with transaction lock to prevent race conditions."""
        if not _validate_user_id(user_id, "subtract_user_balance"):
            logger.error("SUBTRACT_BALANCE_REJECTED user_id=%s amount=%.2f reason=invalid_user_id", user_id, amount)
            return False
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Ensure file exists
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balances_file,
                )
                # Lock row and get current balance
                payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balances_file,
                )
                balances = self._coerce_payload(payload, filename=self.balances_file)
                # Filter garbage keys before processing
                balances = _filter_garbage_keys_storage(balances, self.balances_file)
                balance_before = _safe_float(balances.get(str(user_id), 0.0), field=f"balance[{user_id}]")
                
                if balance_before < amount:
                    logger.warning(
                        "Insufficient balance: user_id=%s required=%.2f available=%.2f",
                        user_id,
                        amount,
                        balance_before,
                    )
                    return False
                    
                new_balance = balance_before - amount
                if new_balance < 0:
                    logger.error("Negative balance prevented user_id=%s new_balance=%.2f", user_id, new_balance)
                    return False
                    
                balances[str(user_id)] = new_balance
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balances_file,
                    json.dumps(balances),
                )
        logger.info(
            "BALANCE_SUBTRACT user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return True

    @_retry_transient
    async def charge_balance_once(
        self,
        user_id: int,
        amount: float,
        *,
        task_id: str,
        sku_id: str = "",
        model_id: str = "",
    ) -> Dict[str, Any]:
        if not _validate_user_id(user_id, "charge_balance_once"):
            logger.error("CHARGE_BALANCE_REJECTED user_id=%s task_id=%s reason=invalid_user_id", user_id, task_id)
            return {"status": "invalid_user_id", "balance_before": 0.0, "balance_after": 0.0}
        if not task_id:
            return {"status": "missing_task_id"}
        if not math.isfinite(amount) or amount <= 0:
            balance_before = await self.get_user_balance(user_id)
            logger.warning(
                "INVALID_CHARGE_AMOUNT user_id=%s amount=%.4f task_id=%s",
                user_id,
                amount,
                task_id,
            )
            return {
                "status": "invalid_amount",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balances_file,
                )
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.balance_deductions_file,
                )

                balances_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balances_file,
                )
                deductions_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.balance_deductions_file,
                )
                balances = self._coerce_payload(balances_payload, filename=self.balances_file)
                deductions = self._coerce_payload(deductions_payload, filename=self.balance_deductions_file)
                # Filter garbage keys
                balances = _filter_garbage_keys_storage(balances, self.balances_file)
                deductions = _filter_garbage_keys_storage(deductions, self.balance_deductions_file)

                if task_id in deductions:
                    balance_before = _safe_float(balances.get(str(user_id), 0.0), field=f"balance[{user_id}]")
                    logger.info(
                        "BALANCE_CHARGE_DUPLICATE user_id=%s task_id=%s sku_id=%s model_id=%s balance=%.2f",
                        user_id,
                        task_id,
                        sku_id,
                        model_id,
                        balance_before,
                    )
                    return {
                        "status": "duplicate",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balance_before = _safe_float(balances.get(str(user_id), 0.0), field=f"balance[{user_id}]")
                if balance_before < amount:
                    logger.warning(
                        "BALANCE_CHARGE_INSUFFICIENT user_id=%s task_id=%s required=%.2f available=%.2f",
                        user_id,
                        task_id,
                        amount,
                        balance_before,
                    )
                    return {
                        "status": "insufficient",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balance_after = balance_before - amount
                if balance_after < 0:
                    logger.error(
                        "BALANCE_CHARGE_NEGATIVE_BLOCKED user_id=%s task_id=%s balance_before=%.2f amount=%.2f",
                        user_id,
                        task_id,
                        balance_before,
                        amount,
                    )
                    return {
                        "status": "negative_blocked",
                        "balance_before": balance_before,
                        "balance_after": balance_before,
                    }

                balances[str(user_id)] = balance_after
                deductions[task_id] = {
                    "user_id": user_id,
                    "model_id": model_id,
                    "sku_id": sku_id,
                    "amount": amount,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(
                    "BALANCE_CHARGE_OK user_id=%s task_id=%s sku_id=%s model_id=%s amount=%.2f balance_after=%.2f",
                    user_id,
                    task_id,
                    sku_id,
                    model_id,
                    amount,
                    balance_after,
                )

                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balances_file,
                    json.dumps(balances) if balances else "{}",
                )
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.balance_deductions_file,
                    json.dumps(deductions) if deductions else "{}",
                )
                return {
                    "status": "charged",
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                }

    async def get_user_language(self, user_id: int) -> str:
        data = await self._load_json(self.languages_file)
        return data.get(str(user_id), "ru")

    async def set_user_language(self, user_id: int, language: str) -> None:
        data = await self._load_json(self.languages_file)
        data[str(user_id)] = language
        await self._save_json(self.languages_file, data)

    async def has_claimed_gift(self, user_id: int) -> bool:
        data = await self._load_json(self.gift_claimed_file)
        return data.get(str(user_id), False)

    async def set_gift_claimed(self, user_id: int) -> None:
        data = await self._load_json(self.gift_claimed_file)
        data[str(user_id)] = True
        await self._save_json(self.gift_claimed_file, data)

    async def get_user_free_generations_today(self, user_id: int) -> int:
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if user_key not in data:
            return 0
        user_data = data[user_key]
        if user_data.get("date") == today:
            return user_data.get("count", 0)
        return 0

    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        from app.pricing.free_policy import get_free_daily_limit

        free_per_day = get_free_daily_limit()
        used = await self.get_user_free_generations_today(user_id)
        return max(0, free_per_day - used)

    async def increment_free_generations(self, user_id: int) -> None:
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        if user_key not in data:
            data[user_key] = {"date": today, "count": 0, "bonus": 0}
        user_data = data[user_key]
        if user_data.get("date") != today:
            user_data["date"] = today
            user_data["count"] = 0
        old_count = max(0, int(user_data.get("count", 0)))
        user_data["count"] = old_count + 1
        await self._save_json(self.free_generations_file, data)
        logger.info("Free gen incremented user_id=%s date=%s count=%s", user_id, today, old_count + 1)

    @_retry_transient
    async def consume_free_generation_once(
        self,
        user_id: int,
        *,
        task_id: str,
        sku_id: str = "",
        source: str = "delivery",
    ) -> Dict[str, Any]:
        if not _validate_user_id(user_id, "consume_free_generation_once"):
            logger.error("CONSUME_FREE_GEN_REJECTED user_id=%s task_id=%s reason=invalid_user_id", user_id, task_id)
            return {"status": "invalid_user_id", "used_today": 0, "remaining": 0, "limit_per_day": 0}
        if not task_id:
            return {"status": "missing_task_id"}
        from app.pricing.free_policy import get_free_daily_limit

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.free_generations_file,
                )
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.free_deductions_file,
                )

                free_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.free_generations_file,
                )
                deductions_payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.free_deductions_file,
                )
                free_data = self._coerce_payload(free_payload, filename=self.free_generations_file)
                deductions = self._coerce_payload(deductions_payload, filename=self.free_deductions_file)
                # Filter garbage keys
                free_data = _filter_garbage_keys_storage(free_data, self.free_generations_file)
                deductions = _filter_garbage_keys_storage(deductions, self.free_deductions_file)

                today = datetime.now().strftime("%Y-%m-%d")
                user_key = str(user_id)
                entry = free_data.get(user_key, {})
                if entry.get("date") != today:
                    entry = {"date": today, "count": 0, "bonus": 0}
                used_count = max(0, int(entry.get("count", 0)))
                limit = int(get_free_daily_limit())
                remaining = max(0, limit - used_count)

                if task_id in deductions:
                    return {
                        "status": "duplicate",
                        "used_today": used_count,
                        "remaining": remaining,
                        "limit_per_day": limit,
                    }

                if remaining <= 0:
                    return {
                        "status": "deny",
                        "used_today": used_count,
                        "remaining": 0,
                        "limit_per_day": limit,
                    }

                entry["count"] = used_count + 1
                free_data[user_key] = entry
                deductions[task_id] = {
                    "user_id": user_id,
                    "sku_id": sku_id,
                    "source": source,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.free_generations_file,
                    json.dumps(free_data) if free_data else "{}",
                )
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.free_deductions_file,
                    json.dumps(deductions) if deductions else "{}",
                )
                remaining = max(0, limit - int(entry.get("count", 0)))
                return {
                    "status": "ok",
                    "used_today": int(entry.get("count", 0)),
                    "remaining": remaining,
                    "limit_per_day": limit,
                }

    async def get_hourly_free_usage(self, user_id: int) -> Dict[str, Any]:
        data = await self._load_json(self.hourly_free_usage_file)
        return data.get(str(user_id), {})

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        data = await self._load_json(self.hourly_free_usage_file)
        data[str(user_id)] = {
            "window_start_iso": window_start_iso,
            "used_count": int(used_count),
        }
        await self._save_json(self.hourly_free_usage_file, data)

    async def get_referral_free_bank(self, user_id: int) -> int:
        data = await self._load_json(self.referral_free_bank_file)
        return int(data.get(str(user_id), 0))

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        data = await self._load_json(self.referral_free_bank_file)
        data[str(user_id)] = int(max(0, remaining_count))
        await self._save_json(self.referral_free_bank_file, data)

    @_retry_transient
    async def add_referral_free_bank(self, user_id: int, bonus: int) -> int:
        """Add to referral free bank with transaction lock to prevent race conditions."""
        if not _validate_user_id(user_id, "add_referral_free_bank"):
            logger.error("ADD_REFERRAL_BANK_REJECTED user_id=%s bonus=%d reason=invalid_user_id", user_id, bonus)
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO storage_json (partner_id, filename, payload) VALUES ($1, $2, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING",
                    self.partner_id,
                    self.referral_free_bank_file,
                )
                payload = await conn.fetchval(
                    "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                    self.partner_id,
                    self.referral_free_bank_file,
                )
                data = self._coerce_payload(payload, filename=self.referral_free_bank_file)
                # Filter garbage keys
                data = _filter_garbage_keys_storage(data, self.referral_free_bank_file)
                current = int(data.get(str(user_id), 0))
                new_total = current + bonus
                data[str(user_id)] = new_total
                await conn.execute(
                    "UPDATE storage_json SET payload=$3::jsonb, updated_at=now() "
                    "WHERE partner_id=$1 AND filename=$2",
                    self.partner_id,
                    self.referral_free_bank_file,
                    json.dumps(data),
                )
        logger.info(
            "REFERRAL_FREE_BANK_ADD user_id=%s bonus=%d before=%d after=%d",
            user_id, bonus, current, new_total,
        )
        return new_total

    async def get_admin_limit(self, user_id: int) -> float:
        from app.config import get_settings

        settings = get_settings()
        if user_id == settings.admin_id:
            return float("inf")
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get("limit", 100.0))

    async def get_admin_spent(self, user_id: int) -> float:
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get("spent", 0.0))

    async def get_admin_remaining(self, user_id: int) -> float:
        limit = await self.get_admin_limit(user_id)
        if limit == float("inf"):
            return float("inf")
        spent = await self.get_admin_spent(user_id)
        return max(0.0, limit - spent)

    # ==================== GENERATION JOBS ====================

    _TERMINAL_JOB_STATUSES = frozenset({
        "done", "delivered", "completed", "failed", "canceled", "success",
        "timeout", "error", "refunded",
    })
    _JOBS_MAX_AGE_HOURS = int(os.getenv("JOBS_PRUNE_MAX_AGE_HOURS", "24"))
    _JOBS_MAX_KEEP = int(os.getenv("JOBS_PRUNE_MAX_KEEP", "200"))

    async def _prune_old_jobs(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove terminal jobs older than _JOBS_MAX_AGE_HOURS, keep at most _JOBS_MAX_KEEP."""
        if len(data) <= self._JOBS_MAX_KEEP:
            return data
        cutoff = (datetime.now() - timedelta(hours=self._JOBS_MAX_AGE_HOURS)).isoformat()
        to_remove = []
        for jid, job in data.items():
            if not isinstance(job, dict):
                to_remove.append(jid)
                continue
            status = (job.get("status") or "").lower()
            updated = job.get("updated_at") or job.get("created_at") or ""
            if status in self._TERMINAL_JOB_STATUSES and updated < cutoff:
                to_remove.append(jid)
        if to_remove:
            for jid in to_remove:
                del data[jid]
            logger.info("JOBS_PRUNED removed=%d remaining=%d cutoff=%s", len(to_remove), len(data), cutoff)
        return data

    async def add_generation_job(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        price: float,
        task_id: Optional[str] = None,
        status: str = "pending",
        *,
        job_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        prompt: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        sku_id: Optional[str] = None,
        is_free: bool = False,
        is_admin_user: bool = False,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        result_url: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> str:
        import uuid

        job_id = job_id or task_id or str(uuid.uuid4())
        data = await self._load_json(self.jobs_file)
        data = await self._prune_old_jobs(data)
        job = {
            "job_id": job_id,
            "request_id": request_id,
            "correlation_id": correlation_id or request_id,
            "user_id": user_id,
            "model_id": model_id,
            "model_name": model_name,
            "prompt": prompt,
            "prompt_hash": prompt_hash,
            "sku_id": sku_id,
            "is_free": bool(is_free),
            "is_admin_user": bool(is_admin_user),
            "params": params,
            "price": price,
            "status": status,
            "task_id": task_id,
            "external_task_id": task_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result_urls": [],
            "result_url": result_url,
            "error_message": None,
            "error_code": error_code,
        }
        data[job_id] = job
        await self._save_json(self.jobs_file, data)
        return job_id

    async def update_job_task_id(self, job_id: str, task_id: str) -> None:
        """Update job with task_id after KIE task creation."""
        data = await self._load_json(self.jobs_file)
        if job_id not in data:
            logger.warning("update_job_task_id: job_id=%s not found", job_id)
            return
        job = data[job_id]
        job["task_id"] = task_id
        job["external_task_id"] = task_id
        job["updated_at"] = datetime.now().isoformat()
        await self._save_json(self.jobs_file, data)
        logger.info("JOB_TASK_ID_UPDATED job_id=%s task_id=%s", job_id, task_id)

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        result_url: Optional[str] = None,
    ) -> None:
        data = await self._load_json(self.jobs_file)
        if job_id not in data:
            raise ValueError(f"Job {job_id} not found")
        job = data[job_id]
        current_status = str(job.get("status") or "").lower()
        new_status = str(status or "").lower()
        if current_status == "delivered" and new_status != "delivered":
            logger.warning(
                "Skipping status regression for delivered job: job_id=%s current=%s next=%s",
                job_id,
                current_status,
                new_status,
            )
            return
        job["status"] = status
        job["updated_at"] = datetime.now().isoformat()
        if result_urls is not None:
            job["result_urls"] = result_urls
            if result_urls:
                job["result_url"] = result_urls[0]
        if error_message is not None:
            job["error_message"] = error_message
        if error_code is not None:
            job["error_code"] = error_code
        if result_url is not None:
            job["result_url"] = result_url
        await self._save_json(self.jobs_file, data)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        return data.get(job_id)

    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        # Filter only valid dict records, log invalid ones
        jobs = []
        for key, val in data.items():
            if isinstance(val, dict):
                jobs.append(val)
            else:
                logger.warning("LIST_JOBS_INVALID_RECORD key=%s type=%s", key, type(val).__name__)
        if user_id is not None:
            jobs = [j for j in jobs if j.get("user_id") == user_id]
        if status is not None:
            jobs = [j for j in jobs if j.get("status") == status]
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs[:limit]

    async def list_jobs_by_status(
        self,
        statuses: List[str],
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        wanted = {status.lower() for status in statuses}
        jobs = []
        for key, job in data.items():
            if not isinstance(job, dict):
                logger.warning("LIST_JOBS_BY_STATUS_INVALID_RECORD key=%s type=%s", key, type(job).__name__)
                continue
            if (job.get("status") or "").lower() in wanted:
                jobs.append(job)
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs[:limit]

    async def add_generation_to_history(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        result_urls: List[str],
        price: float,
        operation_id: Optional[str] = None,
    ) -> str:
        import uuid
        from app.services.history_service import append_event

        gen_id = operation_id or str(uuid.uuid4())
        data = await self._load_json(self.generations_history_file)
        user_key = str(user_id)
        if user_key not in data:
            data[user_key] = []
        generation = {
            "id": gen_id,
            "model_id": model_id,
            "model_name": model_name,
            "params": params,
            "result_urls": result_urls,
            "price": price,
            "timestamp": datetime.now().isoformat(),
        }
        data[user_key].append(generation)
        data[user_key] = data[user_key][-100:]
        await self._save_json(self.generations_history_file, data)
        await append_event(
            self,
            user_id=user_id,
            kind="generation",
            payload={
                "model_id": model_id,
                "model_name": model_name,
                "price": price,
                "result_urls": result_urls,
            },
            event_id=gen_id,
        )
        return gen_id

    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        data = await self._load_json(self.generations_history_file)
        history = data.get(str(user_id), [])
        return history[-limit:]

    # ==================== PAYMENTS ====================

    async def add_payment(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_id: Optional[str] = None,
        screenshot_file_id: Optional[str] = None,
        status: str = "pending",
    ) -> str:
        import uuid

        pay_id = payment_id or str(uuid.uuid4())
        data = await self._load_json(self.payments_file)
        payment = {
            "payment_id": pay_id,
            "user_id": user_id,
            "amount": amount,
            "payment_method": payment_method,
            "screenshot_file_id": screenshot_file_id,
            "status": status,
            "balance_charged": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "admin_id": None,
            "notes": None,
        }
        data[pay_id] = payment
        await self._save_json(self.payments_file, data)
        return pay_id

    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> None:
        data = await self._load_json(self.payments_file)
        if payment_id not in data:
            raise ValueError(f"Payment {payment_id} not found")
        payment = data[payment_id]
        prev_status = payment.get("status")
        if prev_status == status:
            logger.info(
                "PAYMENT_STATUS_IDEMPOTENT payment_id=%s status=%s user_id=%s",
                payment_id,
                status,
                payment.get("user_id"),
            )
        success_statuses = {"approved", "completed"}
        credit_balance = status in success_statuses and not payment.get("balance_charged")
        if credit_balance:
            payment["balance_charged"] = True
        payment["status"] = status
        payment["updated_at"] = datetime.now().isoformat()
        if admin_id is not None:
            payment["admin_id"] = admin_id
        if notes is not None:
            payment["notes"] = notes
        if credit_balance:
            await self.add_user_balance(payment["user_id"], payment["amount"])
        await self._save_json(self.payments_file, data)

    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        data = await self._load_json(self.payments_file)
        return data.get(payment_id)

    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.payments_file)
        payments = list(data.values())
        if user_id is not None:
            payments = [p for p in payments if p.get("user_id") == user_id]
        if status is not None:
            payments = [p for p in payments if p.get("status") == status]
        payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return payments[:limit]

    # ==================== REFERRALS ====================

    @_retry_transient
    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO referrals (partner_id, referred_user_id, referrer_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (partner_id, referred_user_id) DO NOTHING
                """,
                self.partner_id,
                int(user_id),
                int(referrer_id),
            )

    @_retry_transient
    async def get_referrer(self, user_id: int) -> Optional[int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT referrer_id FROM referrals WHERE partner_id=$1 AND referred_user_id=$2",
                self.partner_id,
                int(user_id),
            )
            if row:
                return int(row["referrer_id"])
        return None

    @_retry_transient
    async def get_referrals(self, referrer_id: int) -> List[int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT referred_user_id FROM referrals WHERE partner_id=$1 AND referrer_id=$2",
                self.partner_id,
                int(referrer_id),
            )
            return [int(row["referred_user_id"]) for row in rows]

    async def add_referral_bonus(self, referrer_id: int, bonus: float = 5) -> None:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            key = str(referrer_id)
            data[key] = float(data.get(key, 0.0)) + bonus
            return data

        await self.update_json_file(self.free_generations_file, updater)

    @_retry_transient
    async def create_referral_record(
        self,
        *,
        referrer_id: int,
        referred_user_id: int,
        partner_id: str,
        ref_param: Optional[str],
        bonus_amount: int,
    ) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO referrals (
                    partner_id,
                    referred_user_id,
                    referrer_id,
                    ref_param,
                    bonus_amount,
                    bonus_granted_at
                )
                VALUES ($1, $2, $3, $4, $5, now())
                ON CONFLICT (partner_id, referred_user_id) DO NOTHING
                """,
                partner_id,
                int(referred_user_id),
                int(referrer_id),
                ref_param,
                int(bonus_amount),
            )
            return result.startswith("INSERT")

    @_retry_transient
    async def get_referral_stats(self, referrer_id: int, partner_id: str) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS invited,
                    COUNT(created_at) AS activated,
                    COUNT(bonus_granted_at) AS granted,
                    COALESCE(SUM(bonus_amount), 0) AS bonus_total
                FROM referrals
                WHERE partner_id=$1 AND referrer_id=$2
                """,
                partner_id,
                int(referrer_id),
            )
            if not row:
                return {"invited": 0, "activated": 0, "granted": 0, "bonus_total": 0}
            return {
                "invited": int(row["invited"] or 0),
                "activated": int(row["activated"] or 0),
                "granted": int(row["granted"] or 0),
                "bonus_total": int(row["bonus_total"] or 0),
            }

    @_retry_transient
    async def list_recent_referrals(self, *, partner_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT referrer_id, referred_user_id, created_at, bonus_granted_at, bonus_amount
                FROM referrals
                WHERE partner_id=$1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                partner_id,
                int(limit),
            )
            return [
                {
                    "referrer_id": int(row["referrer_id"]),
                    "referred_user_id": int(row["referred_user_id"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "bonus_granted_at": row["bonus_granted_at"].isoformat() if row["bonus_granted_at"] else None,
                    "bonus_amount": int(row["bonus_amount"] or 0),
                }
                for row in rows
            ]

    @_retry_transient
    async def get_referral_admin_summary(self, *, partner_id: str, limit: int = 5) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            totals_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS invited,
                    COUNT(bonus_granted_at) AS granted,
                    COALESCE(SUM(bonus_amount), 0) AS bonus_total
                FROM referrals
                WHERE partner_id=$1
                """,
                partner_id,
            )
            recent_rows = await conn.fetch(
                """
                SELECT referrer_id, referred_user_id, created_at, bonus_granted_at, bonus_amount
                FROM referrals
                WHERE partner_id=$1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                partner_id,
                int(limit),
            )
        totals = {
            "invited": int(totals_row["invited"] or 0) if totals_row else 0,
            "granted": int(totals_row["granted"] or 0) if totals_row else 0,
            "bonus_total": int(totals_row["bonus_total"] or 0) if totals_row else 0,
        }
        recent = [
            {
                "referrer_id": int(row["referrer_id"]),
                "referred_user_id": int(row["referred_user_id"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "bonus_granted_at": row["bonus_granted_at"].isoformat() if row["bonus_granted_at"] else None,
                "bonus_amount": int(row["bonus_amount"] or 0),
            }
            for row in recent_rows
        ]
        return {"totals": totals, "recent": recent}

    # ==================== GENERIC JSON FILES ====================

    async def read_json_file(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"postgres_storage.read:{filename}")
        payload = await self._load_json(filename)
        if payload:
            return payload
        return default or {}

    async def write_json_file(self, filename: str, data: Dict[str, Any]) -> None:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"postgres_storage.write:{filename}")
        await self._save_json(filename, data)

    @_retry_transient
    async def update_json_file(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        lock_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"postgres_storage.update:{filename}")
        db_query_start = time.monotonic()
        pool = await self._get_pool()
        lock_key = self._advisory_lock_key_pair(filename)
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    from app.utils.pg_advisory_lock import (
                        acquire_advisory_xact_lock,
                        log_advisory_lock_key,
                        try_acquire_advisory_xact_lock,
                    )

                    correlation_id = get_correlation_id() or "corr-na"
                    resolved_lock_mode = lock_mode
                    if resolved_lock_mode is None:
                        resolved_lock_mode = (
                            "pg_try_advisory_xact_lock"
                            if filename == "observability_correlations.json"
                            else "pg_advisory_xact_lock"
                        )
                    log_advisory_lock_key(
                        logger,
                        lock_key,
                        correlation_id=correlation_id,
                        action=resolved_lock_mode,
                    )
                    lock_start = time.monotonic()
                    try:
                        if resolved_lock_mode == "pg_try_advisory_xact_lock":
                            acquired = await try_acquire_advisory_xact_lock(conn, lock_key)
                            if not acquired:
                                lock_duration_ms = int((time.monotonic() - lock_start) * 1000)
                                global _corr_lock_drop_total
                                _corr_lock_drop_total += 1
                                logger.warning(
                                    "CORR_DROP_LOCK_BUSY filename=%s duration_ms=%s correlation_id=%s",
                                    filename,
                                    lock_duration_ms,
                                    correlation_id,
                                )
                                logger.info(
                                    "METRIC_GAUGE name=correlation_store_drop_lock_busy_total value=%s",
                                    _corr_lock_drop_total,
                                )
                                log_structured_event(
                                    correlation_id=correlation_id,
                                    action="CORR_DROP_LOCK_BUSY",
                                    action_path="postgres_storage.update_json_file",
                                    stage="STORAGE_LOCK",
                                    outcome="drop",
                                    lock_key=f"{self.partner_id}:{filename}",
                                    lock_wait_ms_total=lock_duration_ms,
                                    lock_attempts=1,
                                    lock_acquired=False,
                                    param={
                                        "lock_mode": "pg_try_advisory_xact_lock",
                                        "filename": filename,
                                        "lock_key_pair": [lock_key.key_a, lock_key.key_b],
                                    },
                                    skip_correlation_store=True,
                                )
                                return {}
                        else:
                            await acquire_advisory_xact_lock(conn, lock_key)
                    except Exception as exc:
                        lock_duration_ms = int((time.monotonic() - lock_start) * 1000)
                        logger.error(
                            "PG_ADVISORY_XACT_LOCK_FAILED filename=%s duration_ms=%s correlation_id=%s error=%s",
                            filename,
                            lock_duration_ms,
                            correlation_id,
                            exc,
                            exc_info=True,
                        )
                        raise
                    lock_duration_ms = int((time.monotonic() - lock_start) * 1000)
                    if resolved_lock_mode == "pg_try_advisory_xact_lock":
                        logger.info(
                            "PG_TRY_ADVISORY_XACT_LOCK_ACQUIRED filename=%s duration_ms=%s correlation_id=%s",
                            filename,
                            lock_duration_ms,
                            correlation_id,
                        )
                    else:
                        logger.info(
                            "PG_ADVISORY_XACT_LOCK_ACQUIRED filename=%s duration_ms=%s correlation_id=%s",
                            filename,
                            lock_duration_ms,
                            correlation_id,
                        )
                    log_structured_event(
                        correlation_id=correlation_id,
                        action="STORAGE_LOCK",
                        action_path="postgres_storage.update_json_file",
                        stage="STORAGE_LOCK",
                        outcome="acquired",
                        lock_key=f"{self.partner_id}:{filename}",
                        lock_wait_ms_total=lock_duration_ms,
                        lock_attempts=1,
                        lock_acquired=True,
                        lock_backend="postgres",
                        param={
                            "lock_mode": resolved_lock_mode,
                            "filename": filename,
                            "lock_key_pair": [lock_key.key_a, lock_key.key_b],
                        },
                        skip_correlation_store=True,
                    )
                    row = await conn.fetchrow(
                        "SELECT payload FROM storage_json WHERE partner_id=$1 AND filename=$2 FOR UPDATE",
                        self.partner_id,
                        filename,
                    )
                    current: Dict[str, Any] = {}
                    if row:
                        payload = row[0]
                        if isinstance(payload, dict):
                            current = dict(payload)
                        elif isinstance(payload, str):
                            try:
                                parsed = json.loads(payload)
                            except json.JSONDecodeError:
                                parsed = None
                            if isinstance(parsed, dict):
                                current = parsed
                    updated = update_fn(dict(current))
                    # Filter garbage keys before saving
                    clean_updated = _filter_garbage_keys_storage(updated, filename)
                    
                    # ============================================================
                    # CRITICAL DATA LOSS PROTECTION in update_json_file
                    # ============================================================
                    CRITICAL_FILES = {"payments.json", "user_registry.json", "user_balances.json", "generations_history.json"}
                    current_keys_count = len(current) if isinstance(current, dict) else 0
                    new_keys_count = len(clean_updated) if isinstance(clean_updated, dict) else 0
                    
                    if filename in CRITICAL_FILES:
                        # BLOCK: Never allow update_fn to return empty when current has data
                        if current_keys_count > 0 and new_keys_count == 0:
                            logger.error(
                                "CRITICAL_DATA_LOSS_BLOCKED_UPDATE_JSON file=%s current_keys=%d new_keys=%d "
                                "reason=update_fn_returned_empty partner_id=%s",
                                filename, current_keys_count, new_keys_count, self.partner_id
                            )
                            raise ValueError(
                                f"DATA_LOSS_PROTECTION: update_fn for {filename} returned empty "
                                f"(current has {current_keys_count} records)!"
                            )
                        
                        # Log all updates to critical files
                        logger.info(
                            "CRITICAL_FILE_UPDATE file=%s current_keys=%d new_keys=%d partner_id=%s",
                            filename, current_keys_count, new_keys_count, self.partner_id
                        )
                    
                    payload_json = json.dumps(clean_updated) if isinstance(clean_updated, dict) else "{}"
                    await conn.execute(
                        """
                        INSERT INTO storage_json (partner_id, filename, payload)
                        VALUES ($1, $2, $3::jsonb)
                        ON CONFLICT (partner_id, filename)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                        """,
                        self.partner_id,
                        filename,
                        payload_json,
                    )
                    if filename == "observability_correlations.json":
                        logger.info(
                            "METRIC_GAUGE name=correlation_store_lock_wait_ms_total value=%s filename=%s",
                            lock_duration_ms,
                            filename,
                        )
                    db_query_ms = int((time.monotonic() - db_query_start) * 1000)
                    try:
                        pool_size = pool.get_size() if hasattr(pool, "get_size") else None
                        pool_in_use = pool_size - pool.get_idle_size() if hasattr(pool, "get_idle_size") else None
                        pool_max = pool.get_max_size() if hasattr(pool, "get_max_size") else None
                    except Exception:
                        pool_in_use = None
                        pool_max = None
                    log_structured_event(
                        correlation_id=correlation_id,
                        action="DB_QUERY",
                        action_path="postgres_storage.update_json_file",
                        stage="STORAGE_DB",
                        outcome="ok",
                        db_query_ms=db_query_ms,
                        pool_in_use=pool_in_use,
                        pool_size=pool_max,
                        param={"filename": filename},
                        skip_correlation_store=True,
                    )
                    return clean_updated
        except TRANSIENT_ERRORS:
            raise  # Let @_retry_transient handle these
        except Exception as exc:
            self._maybe_open_circuit(exc, context="update_json")
            raise

    # ==================== UTILITY ====================

    def test_connection(self) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ping())
        logger.warning("[STORAGE] test_connection called inside running loop; use await ping()")
        return True

    async def ping(self) -> bool:
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except TRANSIENT_ERRORS:
            try:
                pool = await self._recreate_pool()
                async with pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                return True
            except Exception as exc:
                logger.warning("[STORAGE] ping_failed partner_id=%s error=%s", self.partner_id, exc)
                return False
        except Exception as exc:
            logger.warning("[STORAGE] ping_failed partner_id=%s error=%s", self.partner_id, exc)
            return False

    async def close(self) -> None:
        pools = list(self._pools.values())
        self._pools.clear()
        self._schema_ready_loops.clear()
        self._file_locks.clear()
        for pool in pools:
            await pool.close()

    async def initialize(self) -> bool:
        """Initialize storage connection and ensure schema."""
        try:
            await self._get_pool()
            return await self.ping()
        except Exception as exc:
            logger.warning("[STORAGE] init_failed partner_id=%s error=%s", self.partner_id, exc)
            return False

    # ==================== MIGRATION HELPERS ====================

    @_retry_transient
    async def has_completed_migration(self, key: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM migrations_meta WHERE key=$1", key)
            return row is not None

    @_retry_transient
    async def mark_migration_done(self, key: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO migrations_meta (key, completed_at) VALUES ($1, now()) ON CONFLICT (key) DO NOTHING",
                key,
            )

    @_retry_transient
    async def is_empty(self) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT count(*) AS c FROM storage_json WHERE partner_id=$1", self.partner_id)
            return not row or row[0] == 0

    async def migrate_from_github(self, github_storage: BaseStorage) -> None:
        """Migrate data from GitHub storage to PostgreSQL.
        
        CRITICAL: This function will NOT overwrite existing data and will NOT
        create empty files. It only migrates non-empty data from source.
        """
        migrate_key = "github_to_postgres"
        if await self.has_completed_migration(migrate_key):
            logger.info("[STORAGE] migration already completed")
            return
        
        files = [
            self.balances_file,
            self.languages_file,
            self.gift_claimed_file,
            self.free_generations_file,
            self.hourly_free_usage_file,
            self.referral_free_bank_file,
            self.admin_limits_file,
            self.generations_history_file,
            self.payments_file,
            self.referrals_file,
            self.jobs_file,
        ]
        
        migrated = []
        skipped_empty = []
        skipped_existing = []
        
        for fname in files:
            try:
                # Check if target already has data
                existing_data = await self._load_json_unlocked(fname)
                existing_keys = len(existing_data) if isinstance(existing_data, dict) else 0
                
                if existing_keys > 0:
                    logger.info("[STORAGE] migrate_skipped file=%s reason=target_has_data keys=%d", fname, existing_keys)
                    skipped_existing.append(fname)
                    continue
                
                # Load from source
                payload = await github_storage.read_json_file(fname, default={})
                source_keys = len(payload) if isinstance(payload, dict) else 0
                
                if source_keys == 0:
                    logger.info("[STORAGE] migrate_skipped file=%s reason=source_empty", fname)
                    skipped_empty.append(fname)
                    continue
                
                # Only migrate if source has data
                await self._save_json(fname, payload)
                migrated.append(fname)
                logger.info("[STORAGE] migrated file=%s keys=%d", fname, source_keys)
                
            except Exception as exc:
                logger.warning("[STORAGE] migrate_failed file=%s error=%s", fname, exc)
        
        await self.mark_migration_done(migrate_key)
        logger.info(
            "[STORAGE] migration_completed migrated=%s skipped_empty=%s skipped_existing=%s",
            ",".join(migrated) if migrated else "none",
            ",".join(skipped_empty) if skipped_empty else "none",
            ",".join(skipped_existing) if skipped_existing else "none"
        )
