"""
Storage layer for database operations (asyncpg-based).

Production-safe with:
- Transactions for atomic operations
- Idempotency for payments
- Connection pooling
- Error handling
"""
import asyncio
import inspect
import logging
from unittest.mock import AsyncMock
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta


try:
    import asyncpg  # type: ignore
    HAS_ASYNCPG = True
except ImportError:  # pragma: no cover
    asyncpg = None
    HAS_ASYNCPG = False

from app.database.schema import apply_schema, verify_schema

logger = logging.getLogger(__name__)


def _to_json_str(value: Any) -> Optional[str]:
    """Serialize dict/list payloads for asyncpg query parameters.

    In some deployments the DB column type (or asyncpg codecs) for JSON/JSONB fields may
    still be treated as TEXT by the driver, which makes passing Python dicts fail with
    `expected str, got dict`. Storing as JSON text is safe and keeps the payload usable.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        # Last resort: never crash a generation because of logging payload serialization.
        return str(value)


# Default database service for handlers that cannot receive DI explicitly (e.g. callback handlers)
_default_db_service: "DatabaseService | None" = None


def set_default_db_service(db_service: "DatabaseService | None") -> None:
    """Configure global fallback DatabaseService for convenience helpers."""

    global _default_db_service
    _default_db_service = db_service


async def ensure_user_exists(
    db_service,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
):
    """
    Idempotent user upsert (avoids FK violations in generation_events).
    
    Args:
        db_service: DatabaseService instance
        user_id: Telegram user ID
        username: Optional username
        first_name: Optional first name
    """
    db = db_service or _default_db_service
    if not db:
        return
    
    try:
        user_service = UserService(db)
        await user_service.get_or_create(user_id, username, first_name)
    except Exception as e:
        logger.warning(f"Failed to ensure user {user_id} exists (non-critical): {e}")


class DatabaseService:
    """Main database service with connection pooling."""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> Any:
        """Backward-compat alias for the underlying asyncpg pool.

        Some modules still reference `db.pool`. We keep `_pool` as the
        canonical attribute to avoid accidental reassignment.
        """
        if self._pool is None:
            raise RuntimeError("Database pool not initialized")
        return self._pool
    
    async def initialize(self):
        """Initialize connection pool and apply schema."""
        if not HAS_ASYNCPG:
            raise ImportError("asyncpg is required for database operations")
        
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        
        # Apply schema
        async with self._pool.acquire() as conn:
            await apply_schema(conn)
            schema_ok = await verify_schema(conn)
            if not schema_ok:
                raise RuntimeError("Schema verification failed")
        
        logger.info("✅ Database initialized with schema")
    
    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Database pool closed")
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager for transactions."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    async def acquire(self):
        """Acquire connection from pool."""
        return await self._pool.acquire()
    
    async def release(self, conn):
        """Release connection back to pool."""
        await self._pool.release(conn)
    
    @asynccontextmanager
    async def get_connection(self):
        """Get connection context manager (compatible with FreeModelManager, AdminService, etc)."""
        conn = await self._pool.acquire()
        try:
            yield conn
        finally:
            await self._pool.release(conn)
    
    # Convenience methods for direct queries (auto-acquire connection)
    async def execute(self, query: str, *args):
        """Execute query without returning results."""
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetchrow(self, query: str, *args):
        """Fetch single row."""
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchone(self, query: str, *args):
        """Alias for fetchrow for compatibility."""
        return await self.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """Fetch single value."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def fetch(self, query: str, *args):
        """Fetch all rows."""
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)


class UserService:
    """User management operations."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
    
    async def get_or_create(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        # Backward-compat: some callers historically passed `full_name`
        full_name: str | None = None,
    ) -> Dict[str, Any]:
        """Get or create user.

        Returns row dict + `created_just_now` boolean for idempotent welcome credit flows.
        """
        if first_name is None and full_name is not None:
            first_name = full_name
        async with self.db.transaction() as conn:
            # Try to get existing user
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id
            )
            
            if user:
                # Update last_seen
                await conn.execute(
                    "UPDATE users SET last_seen_at = NOW() WHERE user_id = $1",
                    user_id
                )
                out = dict(user)
                out["created_just_now"] = False
                return out
            
            # Create new user + wallet
            user = await conn.fetchrow("""
                INSERT INTO users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                RETURNING *
            """, user_id, username, first_name)
            
            # Create wallet
            await conn.execute("""
                INSERT INTO wallets (user_id, balance_rub, hold_rub)
                VALUES ($1, 0.00, 0.00)
            """, user_id)
            
            logger.info(f"Created new user {user_id}")
            out = dict(user)
            out["created_just_now"] = True
            return out

    async def get_metadata(self, user_id: int) -> Dict[str, Any]:
        """Get user's metadata JSON."""
        async with self.db.transaction() as conn:
            meta = await conn.fetchval(
                "SELECT metadata FROM users WHERE user_id = $1",
                user_id,
            )
            # Some tests/mock layers return an awaitable for metadata; unwrap it to avoid
            # unawaited coroutine warnings and to keep the return type stable.
            if inspect.isawaitable(meta) or isinstance(meta, AsyncMock):
                meta = await meta
            return dict(meta or {})

    async def merge_metadata(self, user_id: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Shallow-merge metadata patch (JSONB || patch). Returns updated metadata."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE users SET metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb WHERE user_id = $1",
                user_id,
                patch,
            )
            meta = await conn.fetchval(
                "SELECT metadata FROM users WHERE user_id = $1",
                user_id,
            )
            return dict(meta or {})


# Convenience helpers for handlers -----------------------------------------


async def get_user_by_id(user_id: int, db_service: "DatabaseService | None" = None) -> Dict[str, Any] | None:
    """Fetch a user row by Telegram user_id.

    Falls back to globally injected DatabaseService when explicit instance is
    not provided (used by lightweight callback handlers).
    """

    db = db_service or _default_db_service
    if not db:
        logger.warning("get_user_by_id: no db_service configured; returning None")
        return None

    async with db.get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def merge_user_metadata(
    user_id: int, patch: Dict[str, Any], db_service: "DatabaseService | None" = None
) -> Dict[str, Any]:
    """Shallow-merge metadata for a user (idempotent helper for callbacks)."""

    db = db_service or _default_db_service
    if not db:
        logger.warning("merge_user_metadata: no db_service configured; skipping")
        return {}

    user_service = UserService(db)
    return await user_service.merge_metadata(user_id, patch)


class WalletService:
    """Wallet and balance operations."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
    
    async def get_balance(self, user_id: int) -> Dict[str, Decimal]:
        """Get wallet balance."""
        async with self.db.transaction() as conn:
            wallet = await conn.fetchrow(
                "SELECT balance_rub, hold_rub FROM wallets WHERE user_id = $1",
                user_id
            )
            if not wallet:
                return {"balance_rub": Decimal("0.00"), "hold_rub": Decimal("0.00")}
            return dict(wallet)
    
    async def get_history(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get ledger history."""
        async with self.db.transaction() as conn:
            rows = await conn.fetch("""
                SELECT kind, amount_rub, status, ref, meta, created_at
                FROM ledger
                WHERE user_id = $1 AND status = 'done'
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)
            return [dict(row) for row in rows]
    
    async def topup(self, user_id: int, amount_rub: Decimal, 
                   ref: str, meta: Dict = None) -> bool:
        """Add funds (idempotent)."""
        async with self.db.transaction() as conn:
            # Check idempotency
            existing = await conn.fetchval(
                "SELECT id FROM ledger WHERE ref = $1 AND status = 'done'",
                ref
            )
            if existing:
                logger.warning(f"Topup {ref} already processed")
                return False
            
            # Insert ledger entry
            await conn.execute("""
                INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                VALUES ($1, 'topup', $2, 'done', $3, $4)
            """, user_id, amount_rub, ref, meta or {})
            
            # Update wallet
            await conn.execute("""
                UPDATE wallets
                SET balance_rub = balance_rub + $2,
                    updated_at = NOW()
                WHERE user_id = $1
            """, user_id, amount_rub)
            
            logger.info(f"Topup {user_id}: +{amount_rub} RUB (ref: {ref})")
            return True
    
    async def hold(self, user_id: int, amount_rub: Decimal, 
                  ref: str, meta: Dict = None) -> bool:
        """Hold funds for pending operation."""
        async with self.db.transaction() as conn:
            # Idempotency
            existing = await conn.fetchval(
                "SELECT id FROM ledger WHERE ref = $1 AND kind = 'hold' AND status = 'done'",
                ref,
            )
            if existing:
                logger.warning(f"Hold {ref} already processed")
                return True

            # Check available balance
            wallet = await conn.fetchrow(
                "SELECT balance_rub FROM wallets WHERE user_id = $1 FOR UPDATE",
                user_id
            )
            if not wallet or wallet['balance_rub'] < amount_rub:
                return False
            
            # Insert ledger
            await conn.execute("""
                INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                VALUES ($1, 'hold', $2, 'done', $3, $4)
            """, user_id, amount_rub, ref, meta or {})
            
            # Move balance to hold
            await conn.execute("""
                UPDATE wallets
                SET balance_rub = balance_rub - $2,
                    hold_rub = hold_rub + $2,
                    updated_at = NOW()
                WHERE user_id = $1
            """, user_id, amount_rub)
            
            logger.info(f"Hold {user_id}: {amount_rub} RUB (ref: {ref})")
            return True
    
    async def charge(
        self,
        user_id: int,
        amount_rub: Decimal,
        ref: str,
        meta: Dict = None,
        hold_ref: str | None = None,
    ) -> bool:
        """Charge held funds."""
        async with self.db.transaction() as conn:
            # Idempotency
            existing = await conn.fetchval(
                "SELECT id FROM ledger WHERE ref = $1 AND kind = 'charge' AND status = 'done'",
                ref,
            )
            if existing:
                logger.warning(f"Charge {ref} already processed")
                return True

            # Check hold exists
            wallet = await conn.fetchrow(
                "SELECT hold_rub FROM wallets WHERE user_id = $1 FOR UPDATE",
                user_id
            )
            if not wallet or wallet['hold_rub'] < amount_rub:
                return False

            meta_final = dict(meta or {})
            if hold_ref:
                meta_final.setdefault("hold_ref", hold_ref)
            
            # Insert ledger
            await conn.execute("""
                INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                VALUES ($1, 'charge', $2, 'done', $3, $4)
            """, user_id, amount_rub, ref, meta_final)
            
            # Deduct from hold
            await conn.execute("""
                UPDATE wallets
                SET hold_rub = hold_rub - $2,
                    updated_at = NOW()
                WHERE user_id = $1
            """, user_id, amount_rub)
            
            logger.info(f"Charge {user_id}: -{amount_rub} RUB (ref: {ref})")
            return True
    
    async def refund(
        self,
        user_id: int,
        amount_rub: Decimal,
        ref: str,
        meta: Dict = None,
        hold_ref: str | None = None,
    ) -> bool:
        """Refund.

        If `hold_ref` is provided and there is no corresponding successful charge linked to that hold,
        we treat this as releasing held funds back to balance.

        If a charge already happened (or `hold_ref` is not provided), we top up balance without touching
        aggregated hold, to avoid accidentally releasing other holds.
        """
        async with self.db.transaction() as conn:
            # Check idempotency
            existing = await conn.fetchval(
                "SELECT id FROM ledger WHERE ref = $1 AND kind = 'refund' AND status = 'done'",
                ref
            )
            if existing:
                logger.warning(f"Refund {ref} already processed")
                return True

            meta_final = dict(meta or {})
            if hold_ref:
                meta_final.setdefault("hold_ref", hold_ref)

            from_hold = False
            if hold_ref:
                # If there is no successful charge tied to this hold_ref, this is a "release hold" refund.
                charged = await conn.fetchval(
                    """
                    SELECT id FROM ledger
                    WHERE kind = 'charge'
                      AND status = 'done'
                      AND (meta->>'hold_ref') = $1
                    LIMIT 1
                    """,
                    hold_ref,
                )
                from_hold = not bool(charged)
            
            # Insert ledger
            await conn.execute("""
                INSERT INTO ledger (user_id, kind, amount_rub, status, ref, meta)
                VALUES ($1, 'refund', $2, 'done', $3, $4)
            """, user_id, amount_rub, ref, meta_final)

            if from_hold:
                # Move hold back to balance
                await conn.execute("""
                    UPDATE wallets
                    SET hold_rub = hold_rub - $2,
                        balance_rub = balance_rub + $2,
                        updated_at = NOW()
                    WHERE user_id = $1
                """, user_id, amount_rub)
            else:
                # Post-charge refund (do NOT touch aggregated hold)
                await conn.execute("""
                    UPDATE wallets
                    SET balance_rub = balance_rub + $2,
                        updated_at = NOW()
                    WHERE user_id = $1
                """, user_id, amount_rub)
            
            logger.info(f"Refund {user_id}: +{amount_rub} RUB (ref: {ref})")
            return True

    # ---------------------------------------------------------------------
    # Backward-compatible aliases used by some handlers (marketing flow).
    # ---------------------------------------------------------------------
    async def hold_balance(self, user_id: int, amount_rub: Decimal, ref: str, meta: Dict = None) -> bool:
        return await self.hold(user_id, amount_rub, ref, meta=meta)

    async def charge_balance(
        self,
        user_id: int,
        amount_rub: Decimal,
        ref: str,
        meta: Dict = None,
        hold_ref: str | None = None,
    ) -> bool:
        return await self.charge(user_id, amount_rub, ref, meta=meta, hold_ref=hold_ref)

    async def refund_balance(
        self,
        user_id: int,
        amount_rub: Decimal,
        ref: str,
        meta: Dict = None,
        hold_ref: str | None = None,
    ) -> bool:
        return await self.refund(user_id, amount_rub, ref, meta=meta, hold_ref=hold_ref)


class JobService:
    """Job (generation task) operations."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
    
    async def create(self, user_id: int, model_id: str, category: str,
                    input_json: Any, price_rub: Decimal, 
                    idempotency_key: str) -> Optional[int]:
        """Create new job (idempotent)."""
        async with self.db.transaction() as conn:
            # Check idempotency
            existing = await conn.fetchval(
                "SELECT id FROM jobs WHERE idempotency_key = $1",
                idempotency_key
            )
            if existing:
                logger.warning(f"Job {idempotency_key} already exists")
                return existing
            
            # Insert job
            # Some installations may have legacy DB schemas / codecs where JSON payload columns
            # are effectively treated as TEXT by the driver. In that case passing a Python dict
            # raises: "expected str, got dict". We try native first (keeps JSONB semantics),
            # and fallback to serialized JSON text if needed.
            try:
                job_id = await conn.fetchval("""
                    INSERT INTO jobs (user_id, model_id, category, input_json, price_rub, 
                                     status, idempotency_key)
                    VALUES ($1, $2, $3, $4, $5, 'draft', $6)
                    RETURNING id
                """, user_id, model_id, category, input_json, price_rub, idempotency_key)
            except asyncpg.exceptions.DataError:
                input_payload = _to_json_str(input_json) or "{}"
                job_id = await conn.fetchval("""
                    INSERT INTO jobs (user_id, model_id, category, input_json, price_rub, 
                                     status, idempotency_key)
                    VALUES ($1, $2, $3, $4, $5, 'draft', $6)
                    RETURNING id
                """, user_id, model_id, category, input_payload, price_rub, idempotency_key)
            
            logger.info(f"Created job {job_id} for user {user_id}")
            return job_id
    
    async def get(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        async with self.db.transaction() as conn:
            job = await conn.fetchrow(
                "SELECT * FROM jobs WHERE id = $1",
                job_id
            )
            return dict(job) if job else None
    
    async def update_status(self, job_id: int, status: str,
                           kie_task_id: str = None, kie_status: str = None,
                           result_json: Any = None, error_text: str = None):
        """Update job status."""
        async with self.db.transaction() as conn:
            try:
                await conn.execute("""
                UPDATE jobs
                SET status = $2,
                    kie_task_id = COALESCE($3, kie_task_id),
                    kie_status = COALESCE($4, kie_status),
                    result_json = COALESCE($5, result_json),
                    error_text = COALESCE($6, error_text),
                    updated_at = NOW(),
                    finished_at = CASE WHEN $2 IN ('succeeded', 'failed', 'refunded', 'cancelled') 
                                      THEN NOW() ELSE finished_at END
                WHERE id = $1
                """, job_id, status, kie_task_id, kie_status, result_json, error_text)
            except (asyncpg.exceptions.DataError, TypeError):
                safe_result = _to_json_str(result_json) if result_json is not None else None
                await conn.execute("""
                UPDATE jobs
                SET status = $2,
                    kie_task_id = COALESCE($3, kie_task_id),
                    kie_status = COALESCE($4, kie_status),
                    result_json = COALESCE($5, result_json),
                    error_text = COALESCE($6, error_text),
                    updated_at = NOW(),
                    finished_at = CASE WHEN $2 IN ('succeeded', 'failed', 'refunded', 'cancelled') 
                                      THEN NOW() ELSE finished_at END
                WHERE id = $1
                """, job_id, status, kie_task_id, kie_status, safe_result, error_text)

    async def get_by_kie_task_id(self, kie_task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch job by associated Kie task id."""
        async with self.db.transaction() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE kie_task_id = $1",
                kie_task_id,
            )
            return dict(row) if row else None

    async def mark_replied(self, job_id: int, result_json: Any = None, error_text: str | None = None) -> bool:
        """Atomically set replied_at if not already set.

        Returns True only for the first caller; subsequent calls are no-ops (False).
        """
        async with self.db.transaction() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    UPDATE jobs
                       SET replied_at = NOW(),
                           result_json = COALESCE($2, result_json),
                           error_text = COALESCE($3, error_text),
                           updated_at = NOW()
                     WHERE id = $1 AND replied_at IS NULL
                 RETURNING replied_at
                    """,
                    job_id,
                    result_json,
                    error_text,
                )
            except (asyncpg.exceptions.DataError, TypeError):
                safe_result = _to_json_str(result_json) if result_json is not None else None
                row = await conn.fetchrow(
                    """
                    UPDATE jobs
                       SET replied_at = NOW(),
                           result_json = COALESCE($2, result_json),
                           error_text = COALESCE($3, error_text),
                           updated_at = NOW()
                     WHERE id = $1 AND replied_at IS NULL
                 RETURNING replied_at
                    """,
                    job_id,
                    safe_result,
                    error_text,
                )
            return bool(row)
    
    async def list_user_jobs(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's jobs with result/error fields for history."""
        async with self.db.transaction() as conn:
            rows = await conn.fetch("""
                SELECT id, model_id, status, price_rub, created_at, finished_at,
                       result_json, error_text, replied_at
                  FROM jobs
                 WHERE user_id = $1
              ORDER BY created_at DESC
                 LIMIT $2
            """, user_id, limit)
            return [dict(row) for row in rows]


class UIStateService:
    """UI state management (FSM)."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
    
    async def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get UI state."""
        async with self.db.transaction() as conn:
            state = await conn.fetchrow(
                "SELECT state, data FROM ui_state WHERE user_id = $1",
                user_id
            )
            return dict(state) if state else None
    
    async def set(self, user_id: int, state: str, data: Dict = None, 
                 ttl_minutes: int = 60):
        """Set UI state with TTL."""
        async with self.db.transaction() as conn:
            expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
            await conn.execute("""
                INSERT INTO ui_state (user_id, state, data, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET state = EXCLUDED.state,
                    data = EXCLUDED.data,
                    updated_at = NOW(),
                    expires_at = EXCLUDED.expires_at
            """, user_id, state, data or {}, expires_at)
    
    async def clear(self, user_id: int):
        """Clear UI state."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "DELETE FROM ui_state WHERE user_id = $1",
                user_id
            )
    
    async def cleanup_expired(self):
        """Remove expired states."""
        async with self.db.transaction() as conn:
            deleted = await conn.execute(
                "DELETE FROM ui_state WHERE expires_at < NOW()"
            )
            if deleted != "DELETE 0":
                logger.info(f"Cleaned up expired UI states: {deleted}")
