"""
Singleton lock utilities for preventing multiple bot instances.
"""
import asyncio
import logging
import os
import sys
import time
import threading
import random
from pathlib import Path
from typing import Optional

from app.observability.trace import get_correlation_id
from app.observability.structured_logs import log_critical_event, log_structured_event
from app.utils.pg_advisory_lock import AdvisoryLockKeyPair, build_advisory_lock_key_pair

logger = logging.getLogger(__name__)

# Global state for lock acquisition
_lock_acquired = False
_lock_strict_mode = os.getenv("SINGLETON_LOCK_STRICT", "0").lower() in ("1", "true", "yes")
_lock_mode = "none"
_lock_degraded = False
_lock_degraded_reason: Optional[str] = None
_file_lock_handle = None
_file_lock_path: Optional[Path] = None
_no_db_warned = False
_pg_conn = None
_pg_lock_key: Optional[AdvisoryLockKeyPair] = None
_redis_client = None
_redis_lock_key: Optional[str] = None
_redis_lock_value: Optional[str] = None
_redis_renew_task: Optional[asyncio.Task] = None
_redis_renew_stop: Optional[threading.Event] = None
_redis_renew_loop: Optional[asyncio.AbstractEventLoop] = None
_redis_renew_thread: Optional[threading.Thread] = None


def _is_production_env() -> bool:
    env_name = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
    return env_name in {"prod", "production"}


def _allow_file_fallback() -> bool:
    if os.getenv("SINGLETON_LOCK_ALLOW_FILE_FALLBACK", "").lower() in ("1", "true", "yes"):
        return True
    return not _is_production_env()


def _locks_disabled() -> bool:
    disabled = os.getenv("DISABLE_DB_LOCKS", "0").lower() in ("1", "true", "yes")
    return disabled

def _get_redis_lock_ttl_seconds() -> int:
    try:
        ttl = int(os.getenv("REDIS_LOCK_TTL_SECONDS", "30"))
    except ValueError:
        ttl = 30
    return max(5, ttl)


def _get_redis_renew_interval_seconds(ttl_seconds: int) -> int:
    try:
        interval = int(os.getenv("REDIS_LOCK_RENEW_INTERVAL_SECONDS", "0"))
    except ValueError:
        interval = 0
    if interval <= 0:
        interval = max(1, ttl_seconds // 3)
    return max(1, interval)


def _get_redis_renew_jitter_ratio() -> float:
    try:
        ratio = float(os.getenv("REDIS_LOCK_RENEW_JITTER_RATIO", "0"))
    except ValueError:
        ratio = 0.0
    return max(0.0, min(0.5, ratio))


def _is_test_mode() -> bool:
    return os.getenv("TEST_MODE", "0").lower() in ("1", "true", "yes")


_redis_renew_test_random = random.Random(0)


def _resolve_renew_sleep(base_seconds: float, jitter_ratio: float) -> float:
    jitter = base_seconds * jitter_ratio
    if jitter <= 0:
        return base_seconds
    rng = _redis_renew_test_random if _is_test_mode() else random
    return base_seconds + rng.uniform(0.0, jitter)


def _get_redis_connect_timeout_seconds() -> float:
    try:
        timeout_ms = int(os.getenv("REDIS_LOCK_CONNECT_TIMEOUT_MS", "250"))
    except ValueError:
        timeout_ms = 250
    return max(0.05, timeout_ms / 1000)


def _get_redis_max_wait_seconds() -> float:
    try:
        timeout_ms = int(os.getenv("REDIS_LOCK_MAX_WAIT_MS", "300"))
    except ValueError:
        timeout_ms = 300
    return max(0.05, timeout_ms / 1000)


def _get_redis_connect_attempts() -> int:
    try:
        attempts = int(os.getenv("REDIS_LOCK_CONNECT_ATTEMPTS", "1"))
    except ValueError:
        attempts = 1
    return max(1, attempts)


def _get_pg_lock_connect_timeout_seconds() -> float:
    try:
        timeout_s = float(os.getenv("PG_LOCK_CONNECT_TIMEOUT_SECONDS", "0.6"))
    except ValueError:
        timeout_s = 0.6
    return max(0.1, timeout_s)


async def _stop_redis_renewal() -> None:
    global _redis_renew_task, _redis_renew_stop, _redis_renew_loop, _redis_renew_thread
    if _redis_renew_stop is not None:
        _redis_renew_stop.set()
    if _redis_renew_thread is not None:
        if _redis_renew_loop is not None and _redis_renew_loop.is_running() and _redis_renew_task is not None:
            _redis_renew_loop.call_soon_threadsafe(_redis_renew_task.cancel)
            _redis_renew_loop.call_soon_threadsafe(_redis_renew_loop.stop)
        _redis_renew_thread.join(timeout=2)
        _redis_renew_thread = None
        _redis_renew_task = None
        _redis_renew_loop = None
        _redis_renew_stop = None
        return
    if _redis_renew_task is not None:
        _redis_renew_task.cancel()
        try:
            await _redis_renew_task
        except asyncio.CancelledError:
            pass
        _redis_renew_task = None
    _redis_renew_loop = None
    _redis_renew_stop = None


async def _renew_redis_lock(ttl_seconds: int, interval_seconds: int) -> None:
    global _redis_client, _redis_lock_key, _redis_lock_value
    if _redis_client is None or _redis_lock_key is None or _redis_lock_value is None:
        return
    jitter_ratio = _get_redis_renew_jitter_ratio()
    lua_script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""
    while True:
        if _redis_renew_stop is not None and _redis_renew_stop.is_set():
            break
        try:
            await asyncio.sleep(_resolve_renew_sleep(interval_seconds, jitter_ratio))
        except asyncio.CancelledError:
            break
        try:
            renewed = await _redis_client.eval(
                lua_script,
                1,
                _redis_lock_key,
                _redis_lock_value,
                ttl_seconds,
            )
            if renewed != 1:
                logger.error(
                    "[LOCK] LOCK_MODE=redis lock_renew_failed=true error_code=LOCK_RENEW_FAILED reason=not_owner "
                    "lock_key=%s correlation_id=%s",
                    _redis_lock_key,
                    _redis_lock_value,
                )
                _set_lock_state("redis", False, reason="redis_lock_lost")
                break
            logger.debug(
                "[LOCK] LOCK_MODE=redis lock_renewed=true ttl=%s lock_key=%s correlation_id=%s",
                ttl_seconds,
                _redis_lock_key,
                _redis_lock_value,
            )
        except Exception as exc:
            logger.error(
                "[LOCK] LOCK_MODE=redis lock_renew_failed=true error_code=LOCK_RENEW_EXCEPTION reason=%s "
                "lock_key=%s correlation_id=%s",
                exc,
                _redis_lock_key,
                _redis_lock_value,
            )


def _start_redis_renewal(ttl_seconds: int) -> None:
    global _redis_renew_task, _redis_renew_stop, _redis_renew_loop, _redis_renew_thread
    if _redis_client is None or _redis_lock_key is None or _redis_lock_value is None:
        return
    if _redis_renew_task is not None and not _redis_renew_task.done():
        return
    interval_seconds = _get_redis_renew_interval_seconds(ttl_seconds)
    _redis_renew_stop = threading.Event()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            global _redis_renew_task
            _redis_renew_task = loop.create_task(_renew_redis_lock(ttl_seconds, interval_seconds))
            try:
                loop.run_until_complete(_redis_renew_task)
            except asyncio.CancelledError:
                pass
            finally:
                loop.close()

        _redis_renew_loop = loop
        _redis_renew_thread = threading.Thread(target=_run_loop, name="redis-lock-renewal", daemon=True)
        _redis_renew_thread.start()
        logger.info(
            "[LOCK] LOCK_MODE=redis lock_renewal_thread_started=true ttl=%s interval=%s lock_key=%s correlation_id=%s",
            ttl_seconds,
            interval_seconds,
            _redis_lock_key,
            _redis_lock_value,
        )
        return
    _redis_renew_loop = loop
    _redis_renew_task = loop.create_task(_renew_redis_lock(ttl_seconds, interval_seconds))
    logger.info(
        "[LOCK] LOCK_MODE=redis lock_renewal_started=true ttl=%s interval=%s lock_key=%s correlation_id=%s",
        ttl_seconds,
        interval_seconds,
        _redis_lock_key,
        _redis_lock_value,
    )
# Module-global SingletonLock instance
_singleton_lock_instance = None


def is_lock_acquired() -> bool:
    """Check if singleton lock was acquired."""
    if _locks_disabled():
        return True
    return _lock_acquired


def set_lock_acquired(acquired: bool):
    """Set lock acquisition status."""
    global _lock_acquired
    _lock_acquired = acquired


def is_strict_mode() -> bool:
    """Check if strict mode is enabled (exit on lock conflict)."""
    return _lock_strict_mode


def should_exit_on_lock_conflict() -> bool:
    """Determine if process should exit when lock cannot be acquired."""
    return _lock_strict_mode


def get_safe_mode() -> str:
    """
    Get safe mode status based on lock acquisition.
    
    Returns:
        "active" if lock acquired, "passive" if not acquired
    """
    if is_lock_acquired():
        return "active"
    return "passive"


def get_lock_mode() -> str:
    """Return current lock mode."""
    return _lock_mode


def is_lock_degraded() -> bool:
    """Return whether lock is in degraded mode."""
    return _lock_degraded


def get_lock_degraded_reason() -> Optional[str]:
    """Return degraded reason if any."""
    return _lock_degraded_reason


def get_lock_degradation_notice(lang: str = "ru") -> str:
    """Return a user-facing notice when running in degraded lock mode."""
    if not _lock_degraded:
        return ""
    reason = _lock_degraded_reason or "lock_degraded"
    if lang == "en":
        return (
            "⚠️ The service is running in a degraded mode. Some actions may be slower or require retry.\n"
            f"Reason: {reason}."
        )
    return (
        "⚠️ Сейчас сервис работает в режиме деградации. Возможны задержки или повторные попытки.\n"
        f"Причина: {reason}."
    )


def get_lock_admin_notice(lang: str = "ru") -> str:
    """Return a neutral lock status line for admins only."""
    if not _lock_degraded:
        return ""
    reason = _lock_degraded_reason or "lock_degraded"
    if reason == "LOCK_DISABLED_NO_DB":
        if lang == "en":
            return "ℹ️ Lock disabled (LOCK_DISABLED_NO_DB)."
        return "ℹ️ Блокировка отключена (LOCK_DISABLED_NO_DB)."
    if reason == "file_lock_fallback":
        if lang == "en":
            return "ℹ️ Local-only lock mode active."
        return "ℹ️ Локальный режим блокировки активен."
    if lang == "en":
        return f"ℹ️ Lock status: {reason}."
    return f"ℹ️ Статус блокировки: {reason}."


def _set_lock_state(mode: str, acquired: bool, reason: Optional[str] = None) -> None:
    global _lock_mode, _lock_degraded, _lock_degraded_reason
    _lock_mode = mode
    set_lock_acquired(acquired)
    if reason or not acquired:
        _lock_degraded = True
        _lock_degraded_reason = reason or "lock_not_acquired"
    else:
        _lock_degraded = False
        _lock_degraded_reason = None


def _get_file_lock_path() -> Path:
    lock_dir = Path(os.getenv("SINGLETON_LOCK_DIR", "/app/data"))
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("[LOCK] file_lock_dir_fallback=true reason=%s", exc)
        lock_dir = Path("/tmp")
        lock_dir.mkdir(parents=True, exist_ok=True)
    lock_name = os.getenv("SINGLETON_LOCK_NAME", "trt_webhook_singleton.lock")
    return lock_dir / lock_name


def _acquire_file_lock() -> bool:
    global _file_lock_handle, _file_lock_path
    if _file_lock_handle is not None:
        return True
    _file_lock_path = _get_file_lock_path()
    try:
        _file_lock_handle = open(_file_lock_path, "w")
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_file_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _file_lock_handle.write(f"{os.getpid()}:{time.time()}\n")
        _file_lock_handle.flush()
        logger.info("[LOCK] LOCK_MODE=file lock_path=%s", _file_lock_path)
        return True
    except Exception as exc:
        if _file_lock_handle:
            try:
                _file_lock_handle.close()
            except Exception:
                pass
        _file_lock_handle = None
        logger.warning("[LOCK] LOCK_MODE=file lock_acquire_failed=true reason=%s", exc)
        return False


def _derive_pg_lock_key() -> AdvisoryLockKeyPair:
    global _pg_lock_key
    if _pg_lock_key is not None:
        return _pg_lock_key
    seed = (
        os.getenv("PG_ADVISORY_LOCK_KEY")
        or os.getenv("PARTNER_ID")
        or os.getenv("BOT_INSTANCE_ID")
        or "trt_bot_lock"
    )
    _pg_lock_key = build_advisory_lock_key_pair(source="singleton_lock", payload=seed)
    return _pg_lock_key

async def _acquire_redis_lock(redis_url: str, ttl_seconds: int = 30) -> bool:
    """Acquire lock using Redis SET NX EX."""
    global _redis_client, _redis_lock_key, _redis_lock_value
    try:
        import redis.asyncio as redis  # type: ignore
    except ImportError:
        logger.debug("[LOCK] redis not available, skipping redis lock")
        return False
    
    try:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_REDIS_CONNECT_SLEEP_MS", label="redis_lock.connect")
        connect_timeout = _get_redis_connect_timeout_seconds()
        try:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=connect_timeout,
                socket_timeout=connect_timeout,
            )
        except TypeError:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
        if asyncio.iscoroutine(_redis_client):
            _redis_client = await _redis_client
        _redis_lock_key = f"trt_bot_lock:{os.getenv('BOT_INSTANCE_ID', 'default')}"
        _redis_lock_value = f"{os.getpid()}:{time.time()}"

        acquire_timeout = _get_redis_max_wait_seconds()
        acquired = await asyncio.wait_for(
            _redis_client.set(
                _redis_lock_key,
                _redis_lock_value,
                nx=True,
                ex=ttl_seconds,
            ),
            timeout=acquire_timeout,
        )
        if acquired:
            logger.info("[LOCK] LOCK_MODE=redis lock_acquired=true ttl=%s", ttl_seconds)
            return True
        else:
            await _redis_client.aclose()
            _redis_client = None
            logger.warning("[LOCK] LOCK_MODE=redis lock_acquired=false reason=already_held")
            return False
    except asyncio.TimeoutError:
        logger.warning("[LOCK] LOCK_MODE=redis lock_acquire_failed=true reason=timeout")
        if _redis_client:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
            _redis_client = None
        return False
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=redis lock_acquire_failed=true reason=%s", exc)
        if _redis_client:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
            _redis_client = None
        return False


async def _release_redis_lock() -> None:
    """Release Redis lock."""
    global _redis_client, _redis_lock_key, _redis_lock_value
    if _redis_client is None or _redis_lock_key is None:
        return
    try:
        await _stop_redis_renewal()
    except RuntimeError as exc:
        logger.warning("[LOCK] LOCK_MODE=redis lock_release_failed=true reason=loop_closed error=%s", exc)
        return
    try:
        # Use Lua script for atomic check-and-delete
        lua_script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
        await _redis_client.eval(lua_script, 1, _redis_lock_key, _redis_lock_value)
        logger.info("[LOCK] LOCK_MODE=redis lock_released=true")
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=redis lock_release_failed=true reason=%s", exc)
    finally:
        if _redis_client:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
            _redis_client = None


async def _acquire_postgres_lock(dsn: str) -> bool:
    global _pg_conn
    try:
        import asyncpg  # type: ignore
    except ImportError as exc:
        # Gracefully skip postgres lock if driver not installed (avoid noisy warnings)
        logger.debug("[LOCK] LOCK_MODE=postgres skipped missing_asyncpg=true reason=%s", exc)
        return False

    try:
        conn = await asyncpg.connect(dsn)
        lock_key = _derive_pg_lock_key()
        correlation_id = get_correlation_id() or "corr-na"
        from app.utils.pg_advisory_lock import log_advisory_lock_key

        log_advisory_lock_key(logger, lock_key, correlation_id=correlation_id, action="pg_try_advisory_lock")
        acquired = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1, $2)",
            lock_key.key_a,
            lock_key.key_b,
        )
        if not acquired:
            await conn.close()
            logger.error(
                "[LOCK] LOCK_MODE=postgres lock_acquired=false lock_key_pair_a=%s lock_key_pair_b=%s reason=pg_try_advisory_lock_failed",
                lock_key.key_a,
                lock_key.key_b,
            )
            return False
        _pg_conn = conn
        logger.info(
            "[LOCK] LOCK_MODE=postgres lock_acquired=true lock_key_pair_a=%s lock_key_pair_b=%s",
            lock_key.key_a,
            lock_key.key_b,
        )
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("[LOCK] LOCK_MODE=postgres lock_acquire_failed=true reason=%s", exc)
        return False


async def _release_postgres_lock() -> None:
    global _pg_conn
    if _pg_conn is None:
        return
    lock_key = _derive_pg_lock_key()
    try:
        await _pg_conn.execute(
            "SELECT pg_advisory_unlock($1, $2)",
            lock_key.key_a,
            lock_key.key_b,
        )
        await _pg_conn.close()
        logger.info(
            "[LOCK] LOCK_MODE=postgres lock_released=true lock_key_pair_a=%s lock_key_pair_b=%s",
            lock_key.key_a,
            lock_key.key_b,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("[LOCK] LOCK_MODE=postgres lock_release_failed=true reason=%s", exc)
    finally:
        _pg_conn = None


def _release_file_lock() -> None:
    global _file_lock_handle, _file_lock_path
    if _file_lock_handle is None:
        return
    try:
        if sys.platform != "win32":
            import fcntl

            fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_UN)
        _file_lock_handle.close()
        logger.info("[LOCK] LOCK_MODE=file lock_released=true path=%s", _file_lock_path)
    except Exception as exc:
        logger.error("[LOCK] LOCK_MODE=file lock_release_failed=true reason=%s", exc)
    finally:
        _file_lock_handle = None
        _file_lock_path = None


async def acquire_singleton_lock(dsn=None, *, require_lock: bool = False) -> bool:
    """
    Async function to acquire singleton lock.
    Creates SingletonLock instance and acquires lock.
    
    Args:
        dsn: Optional database connection string
        
    Returns:
        True if lock acquired, False otherwise
    """
    global _singleton_lock_instance
    
    correlation_id = get_correlation_id() or "corr-na"
    lock_started = time.monotonic()
    # Redis first (primary for multi-instance)
    redis_url = os.getenv("REDIS_URL", "").strip() or None
    if _locks_disabled():
        _set_lock_state("disabled", True, reason="lock_disabled_by_env")
        logger.info("[LOCK] singleton_disabled=true reason=disabled_by_env")
        log_structured_event(
            correlation_id=correlation_id,
            action="LOCK_ACQUIRE_DONE",
            action_path="singleton_lock.acquire",
            stage="LOCK",
            outcome="ok",
            lock_backend="disabled",
            lock_wait_ms_total=int((time.monotonic() - lock_started) * 1000),
            lock_attempts=0,
            lock_ttl_s=None,
            param={"reason": "lock_disabled_by_env"},
            skip_correlation_store=True,
        )
        return True

    if redis_url:
        ttl_seconds = _get_redis_lock_ttl_seconds()
        redis_attempts = _get_redis_connect_attempts()
        redis_acquired = False
        log_structured_event(
            correlation_id=correlation_id,
            action="LOCK_ACQUIRE_START",
            action_path="singleton_lock.acquire",
            stage="LOCK",
            outcome="start",
            lock_backend="redis",
            lock_ttl_s=ttl_seconds,
            lock_attempts=redis_attempts,
            param={"redis_url": True},
            skip_correlation_store=True,
        )
        for attempt in range(1, redis_attempts + 1):
            redis_acquired = await _acquire_redis_lock(redis_url, ttl_seconds=ttl_seconds)
            if redis_acquired:
                _set_lock_state("redis", True, reason=None)
                logger.info("[LOCK] LOCK_MODE=redis lock_acquired=true for multi-instance scaling")
                _start_redis_renewal(ttl_seconds)
                log_structured_event(
                    correlation_id=correlation_id,
                    action="LOCK_ACQUIRE_DONE",
                    action_path="singleton_lock.acquire",
                    stage="LOCK",
                    outcome="ok",
                    lock_backend="redis",
                    lock_wait_ms_total=int((time.monotonic() - lock_started) * 1000),
                    lock_attempts=attempt,
                    lock_ttl_s=ttl_seconds,
                    param={"attempt": attempt},
                    skip_correlation_store=True,
                )
                return True
            if attempt < redis_attempts:
                logger.warning(
                    "[LOCK] LOCK_MODE=redis lock_acquire_retry attempt=%s attempts_total=%s",
                    attempt,
                    redis_attempts,
                )
        logger.warning("[LOCK] LOCK_MODE=redis lock_acquired=false reason=redis_lock_failed attempts=%s", redis_attempts)
        log_structured_event(
            correlation_id=correlation_id,
            action="LOCK_STATUS",
            action_path="singleton_lock.acquire",
            stage="LOCK",
            outcome="degraded",
            lock_backend="redis",
            lock_wait_ms_total=int((time.monotonic() - lock_started) * 1000),
            lock_attempts=redis_attempts,
            lock_ttl_s=ttl_seconds,
            param={"degraded_reason": "redis_unavailable"},
            skip_correlation_store=True,
        )

    # Fallback to Postgres advisory lock before file lock.
    pg_dsn = dsn or os.getenv("DATABASE_URL", "").strip()
    if pg_dsn:
        log_structured_event(
            correlation_id=correlation_id,
            action="LOCK_ACQUIRE_START",
            action_path="singleton_lock.acquire",
            stage="LOCK",
            outcome="start",
            lock_backend="postgres",
            lock_attempts=1,
            param={"fallback": True},
            skip_correlation_store=True,
        )
        try:
            pg_timeout = _get_pg_lock_connect_timeout_seconds()
            acquired = await asyncio.wait_for(_acquire_postgres_lock(pg_dsn), timeout=pg_timeout)
        except asyncio.TimeoutError:
            acquired = False
            logger.warning("[LOCK] LOCK_MODE=postgres lock_acquire_failed=true reason=timeout")
            log_critical_event(
                correlation_id=correlation_id,
                update_id=None,
                stage="LOCK",
                latency_ms=None,
                retry_after=None,
                timeout_s=pg_timeout,
                attempt=1,
                error_code="PG_LOCK_TIMEOUT",
                error_id="PG_LOCK_TIMEOUT",
                exception_class="TimeoutError",
                where="singleton_lock.acquire_postgres",
                fix_hint="Check Postgres connectivity and reduce lock contention.",
                retryable=True,
                upstream="db",
                elapsed_ms=pg_timeout * 1000,
            )
        if acquired:
            _set_lock_state("postgres", True, reason="redis_unavailable")
            logger.warning("[LOCK] LOCK_MODE=postgres fallback=true degraded=true reason=redis_unavailable")
            log_structured_event(
                correlation_id=correlation_id,
                action="LOCK_ACQUIRE_DONE",
                action_path="singleton_lock.acquire",
                stage="LOCK",
                outcome="ok",
                lock_backend="postgres",
                lock_wait_ms_total=int((time.monotonic() - lock_started) * 1000),
                lock_attempts=1,
                lock_ttl_s=None,
                param={"degraded_reason": "redis_unavailable"},
                skip_correlation_store=True,
            )
            return True

    # Fallback to file only in non-prod
    storage_mode = os.getenv("STORAGE_MODE", "auto").lower()
    if _allow_file_fallback():
        acquired = _acquire_file_lock()
        if acquired:
            _set_lock_state("file", True, reason="redis_connect_timeout")
            logger.warning(
                "[LOCK] LOCK_MODE=file fallback=true degraded=true single_instance=true "
                "reason=redis_connect_timeout storage_mode=%s",
                storage_mode,
            )
            log_structured_event(
                correlation_id=correlation_id,
                action="LOCK_ACQUIRE_DONE",
                action_path="singleton_lock.acquire",
                stage="LOCK",
                outcome="ok",
                lock_backend="file",
                lock_wait_ms_total=int((time.monotonic() - lock_started) * 1000),
                lock_attempts=1,
                lock_ttl_s=None,
                param={"degraded_reason": "redis_connect_timeout"},
                skip_correlation_store=True,
            )
            return True
        _set_lock_state("file", False, reason="file_lock_failed")
        return False

    logger.error("[LOCK] LOCK_MODE=none reason=redis_unavailable storage_mode=%s", storage_mode)
    _set_lock_state("none", False, reason="redis_unavailable")
    return False


async def release_singleton_lock() -> None:
    """
    Async function to release singleton lock.
    Releases lock if instance exists.
    """
    global _singleton_lock_instance
    
    if _locks_disabled():
        return

    if _singleton_lock_instance is not None:
        try:
            await _singleton_lock_instance.release()
        except RuntimeError as exc:
            logger.warning("LOCK_RELEASE_SKIPPED reason=loop_closed error=%s", exc)
        except Exception as e:
            logger.error(f"Failed to release singleton lock: {e}")
        finally:
            _singleton_lock_instance = None

    if _lock_mode == "redis":
        try:
            await _release_redis_lock()
        except RuntimeError as exc:
            logger.warning("LOCK_RELEASE_SKIPPED reason=loop_closed error=%s", exc)
            return

    if _lock_mode == "postgres":
        try:
            await _release_postgres_lock()
        except RuntimeError as exc:
            logger.warning("LOCK_RELEASE_SKIPPED reason=loop_closed error=%s", exc)
            return

    if _file_lock_handle is not None:
        _release_file_lock()


# Explicit export for importlib compatibility
__all__ = [
    'is_lock_acquired',
    'set_lock_acquired',
    'is_strict_mode',
    'should_exit_on_lock_conflict',
    'get_safe_mode',
    'get_lock_mode',
    'is_lock_degraded',
    'get_lock_degraded_reason',
    'get_lock_degradation_notice',
    'acquire_singleton_lock',
    'release_singleton_lock'
]
