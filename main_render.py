"""Render entrypoint.

Goals:
- Webhook-first runtime (Render Web Service)
- aiogram-only import surface (no python-telegram-bot imports from this module)
- Health endpoints for Render + UptimeRobot
- Singleton advisory lock support (PostgreSQL) to avoid double-processing

This project historically had a PTB (python-telegram-bot) runner. Tests still cover
that legacy in bot_kie.py, but this runtime is aiogram-based.

Important: the repo contains a local ./aiogram folder with tiny test stubs.
In production we must import the real aiogram package from site-packages.
"""

from __future__ import annotations

import contextlib
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aiohttp import web


def _import_real_aiogram_symbols():
    """Import aiogram symbols from site-packages even if ./aiogram stubs exist."""
    project_root = Path(__file__).resolve().parent
    has_local_stubs = (project_root / "aiogram" / "__init__.py").exists()
    removed: list[str] = []

    if has_local_stubs:
        # Remove project root and '' so import machinery does not pick local stubs.
        for entry in list(sys.path):
            if entry in {"", str(project_root)}:
                removed.append(entry)
                try:
                    sys.path.remove(entry)
                except ValueError:
                    pass

    try:
        # Import the package (this will populate sys.modules with the real aiogram).
        import importlib

        importlib.import_module("aiogram")
    finally:
        # Restore path for app imports.
        for entry in reversed(removed):
            sys.path.insert(0, entry)

    # Now import symbols from whichever aiogram got loaded.
    from aiogram import Bot, Dispatcher  # type: ignore
    from aiogram.fsm.storage.memory import MemoryStorage  # type: ignore
    from aiogram.types import Update  # type: ignore
    from aiogram.client.default import DefaultBotProperties  # type: ignore

    return Bot, Dispatcher, MemoryStorage, Update, DefaultBotProperties


Bot, Dispatcher, MemoryStorage, Update, DefaultBotProperties = _import_real_aiogram_symbols()

from app.utils.logging_config import setup_logging  # noqa: E402
from app.utils.runtime_state import runtime_state  # noqa: E402
from app.utils.webhook import get_webhook_base_url  # noqa: E402


logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _derive_secret_path_from_token(token: str) -> str:
    """Derive a stable URL-safe secret path.

    Compatibility note:
    Older deployments used the bot token with ':' removed as the webhook path.
    We keep that behavior as the default to avoid silent 404s after redeploys.
    """

    cleaned = token.strip().replace(":", "")
    # Keep it reasonably short but stable.
    if len(cleaned) > 64:
        cleaned = cleaned[-64:]
    return cleaned


@dataclass(frozen=True)
class RuntimeConfig:
    bot_mode: str
    port: int
    webhook_base_url: str
    webhook_secret_path: str
    webhook_secret_token: str
    telegram_bot_token: str
    database_url: str
    dry_run: bool


def _load_runtime_config() -> RuntimeConfig:
    bot_mode = os.getenv("BOT_MODE", "webhook").strip().lower()
    port_env = os.getenv("PORT")
    port = int(port_env) if port_env else 0
    webhook_base_url = get_webhook_base_url().strip().rstrip("/")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    # Secret path in URL (preferred). Can be explicitly overridden.
    webhook_secret_path = os.getenv("WEBHOOK_SECRET_PATH", "").strip()
    if not webhook_secret_path:
        webhook_secret_path = _derive_secret_path_from_token(telegram_bot_token)

    # Secret token in header (Telegram supports X-Telegram-Bot-Api-Secret-Token)
    webhook_secret_token = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()

    database_url = os.getenv("DATABASE_URL", "").strip()
    dry_run = _bool_env("DRY_RUN", False) or _bool_env("TEST_MODE", False)

    return RuntimeConfig(
        bot_mode=bot_mode,
        port=port,
        webhook_base_url=webhook_base_url,
        webhook_secret_path=webhook_secret_path,
        webhook_secret_token=webhook_secret_token,
        telegram_bot_token=telegram_bot_token,
        database_url=database_url,
        dry_run=dry_run,
    )


@dataclass
class ActiveState:
    active: bool


class SingletonLock:
    """Async wrapper for the sync advisory lock implementation."""

    def __init__(self, database_url: str, *, key: Optional[int] = None):
        self.database_url = database_url
        self.key = key
        self._acquired = False

    async def acquire(self) -> bool:
        # NOTE: app.locking.single_instance.acquire_single_instance_lock() reads DATABASE_URL
        # from env and uses the psycopg2 pool from database.py. We keep this wrapper async
        # for uniformity.
        if not self.database_url:
            self._acquired = True
            return True

        try:
            from app.locking.single_instance import acquire_single_instance_lock

            # Signature has no args (it reads env). Passing args breaks and forces PASSIVE.
            self._acquired = bool(acquire_single_instance_lock())
            return self._acquired
        except Exception as e:
            logger.exception("[LOCK] Failed to acquire singleton lock: %s", e)
            self._acquired = False
            return False

    async def release(self) -> None:
        if not self.database_url:
            return
        if not self._acquired:
            return
        try:
            from app.locking.single_instance import release_single_instance_lock

            release_single_instance_lock()
        except Exception as e:
            logger.warning("[LOCK] Failed to release singleton lock: %s", e)


# Exported name for tests (they monkeypatch this)
try:
    from app.storage.pg_storage import PostgresStorage
except Exception:  # pragma: no cover
    PostgresStorage = object  # type: ignore


async def preflight_webhook(bot: Bot) -> None:
    """Remove webhook to avoid conflict when running polling."""
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("[PRE-FLIGHT] Webhook deleted")
    except Exception as e:
        logger.warning("[PRE-FLIGHT] Failed to delete webhook: %s", e)


def create_bot_application() -> tuple[Dispatcher, Bot]:
    """Create aiogram Dispatcher + Bot (sync factory for tests)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    # aiogram 3.7.0+ requires DefaultBotProperties for parse_mode
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bot = Bot(token=token, default=default_properties)
    dp = Dispatcher(storage=MemoryStorage())

    # Routers
    from bot.handlers import (
        admin_router,
        balance_router,
        diag_router,
        error_handler_router,
        flow_router,
        gallery_router,
        history_router,
        marketing_router,
        quick_actions_router,
        zero_silence_router,
    )

    dp.include_router(error_handler_router)
    dp.include_router(diag_router)
    dp.include_router(admin_router)
    dp.include_router(balance_router)
    dp.include_router(history_router)
    dp.include_router(marketing_router)
    dp.include_router(gallery_router)
    dp.include_router(quick_actions_router)
    dp.include_router(flow_router)
    dp.include_router(zero_silence_router)

    return dp, bot


def _build_webhook_url(cfg: RuntimeConfig) -> str:
    base = cfg.webhook_base_url.rstrip("/")
    return f"{base}/webhook/{cfg.webhook_secret_path}" if base else ""


def _health_payload(active_state: ActiveState) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "active" if active_state.active else "passive",
        "active": bool(active_state.active),
        "bot_mode": runtime_state.bot_mode,
        "storage_mode": runtime_state.storage_mode,
        "lock_acquired": runtime_state.lock_acquired,
        "instance_id": runtime_state.instance_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _make_web_app(
    *,
    dp: Dispatcher,
    bot: Bot,
    cfg: RuntimeConfig,
    active_state: ActiveState,
) -> web.Application:
    app = web.Application()
    # In-memory resilience structures (single instance assumption)
    recent_update_ids: set[int] = set()
    rate_map: dict[str, list[float]] = {}

    def _client_ip(request: web.Request) -> str:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return ip or (request.remote or "unknown")

    def _rate_limited(ip: str, now: float, limit: int = 5, window_s: float = 1.0) -> bool:
        hits = rate_map.get(ip, [])
        hits = [t for t in hits if now - t <= window_s]
        if len(hits) >= limit:
            rate_map[ip] = hits
            return True
        hits.append(now)
        rate_map[ip] = hits
        return False

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def root(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def webhook(request: web.Request) -> web.Response:
        """Webhook handler with full validation and error handling.
        
        Security:
        - Verifies webhook secret path
        - Validates X-Telegram-Bot-Api-Secret-Token header
        - Rate limits and protects against malformed payloads
        
        Errors:
        - 400: Malformed JSON
        - 401: Invalid secret token
        - 404: Invalid path (hides existence)
        - 503: Instance not ready (during rolling deploy)
        - 200: OK (even if processing failed - Telegram will retry)
        """
        secret = request.match_info.get("secret")
        if secret != cfg.webhook_secret_path:
            # Hide existence of endpoint
            raise web.HTTPNotFound()

        # Enforce Telegram header secret if configured
        if cfg.webhook_secret_token:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != cfg.webhook_secret_token:
                logger.warning("[WEBHOOK] Invalid secret token")
                raise web.HTTPUnauthorized()

        if not active_state.active:
            # During rolling deploy, return 503 to force Telegram retry
            # until this instance becomes ACTIVE (acquires lock)
            logger.info("[WEBHOOK] Instance not active (rolling deploy?), returning 503")
            raise web.HTTPServiceUnavailable()

        # Basic rate limiting per IP
        ip = _client_ip(request)
        now = time.time()
        if _rate_limited(ip, now):
            logger.warning("[WEBHOOK] Rate limit exceeded for ip=%s", ip)
            return web.Response(status=200, text="ok")

        # Parse JSON with timeout protection
        try:
            try:
                payload = await asyncio.wait_for(
                    request.json(),
                    timeout=5.0  # 5 second timeout for JSON parsing
                )
            except asyncio.TimeoutError:
                logger.warning("[WEBHOOK] JSON parsing timeout")
                return web.Response(status=400, text="timeout")
        except Exception as e:
            logger.warning("[WEBHOOK] Bad JSON: %s", e)
            return web.Response(status=400, text="bad json")

        # Process update with error isolation and duplicate suppression
        try:
            try:
                update = Update.model_validate(payload)
            except Exception as e:
                logger.warning("[WEBHOOK] Invalid Telegram update: %s", e)
                return web.Response(status=400, text="invalid update")
            
            try:
                update_id = int(getattr(update, "update_id", 0))
            except Exception:
                update_id = 0
            if update_id and update_id in recent_update_ids:
                logger.info("[WEBHOOK] Duplicate update_id=%s ignored", update_id)
                return web.Response(status=200, text="ok")

            # Feed update to dispatcher with timeout
            try:
                await asyncio.wait_for(
                    dp.feed_update(bot, update),
                    timeout=30.0  # 30 second timeout for update processing
                )
            except asyncio.TimeoutError:
                logger.error("[WEBHOOK] Update processing timeout for update_id=%s", 
                           update.update_id)
                # Still return 200 - Telegram will retry if needed
            except Exception as e:
                logger.exception("[WEBHOOK] Error processing update_id=%s: %s",
                               update.update_id, e)
                # Still return 200 - prevent Telegram storm
            else:
                if update_id:
                    recent_update_ids.add(update_id)
        except Exception as e:
            logger.exception("[WEBHOOK] Unexpected error: %s", e)
            # 200 to prevent Telegram retry storm; errors are logged for monitoring
        
        return web.Response(status=200, text="ok")

    app.router.add_get("/health", health)
    app.router.add_get("/", root)
    # aiohttp auto-registers HEAD for GET; explicit add_head causes duplicate route
    app.router.add_post("/webhook/{secret}", webhook)

    async def on_shutdown(_app: web.Application) -> None:
        await bot.session.close()

    app.on_shutdown.append(on_shutdown)
    return app


async def _start_web_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner


async def main() -> None:
    setup_logging()

    cfg = _load_runtime_config()
    effective_bot_mode = cfg.bot_mode
    if effective_bot_mode == "webhook" and not cfg.webhook_base_url:
        logger.warning(
            "[CONFIG] WEBHOOK_BASE_URL missing in webhook mode; falling back to polling"
        )
        effective_bot_mode = "polling"

    runtime_state.bot_mode = effective_bot_mode
    runtime_state.last_start_time = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("STARTUP (aiogram)")
    logger.info("BOT_MODE=%s PORT=%s", effective_bot_mode, cfg.port or "(not set)")
    logger.info("WEBHOOK_BASE_URL=%s", cfg.webhook_base_url or "(not set)")
    logger.info("WEBHOOK_SECRET_PATH=%s", (cfg.webhook_secret_path[:6] + "..."))
    logger.info("WEBHOOK_SECRET_TOKEN=%s", "SET" if cfg.webhook_secret_token else "(not set)")
    logger.info("DRY_RUN=%s", cfg.dry_run)
    logger.info("=" * 60)

    dp, bot = create_bot_application()

    # IMPORTANT: the advisory lock helper in app.locking.single_instance relies on
    # the psycopg2 connection pool from database.py being initialized.
    # If we don't create the pool first, lock acquisition can fail even when no
    # other instance is running, leaving this deploy permanently PASSIVE.
    #
    # SINGLETON_LOCK_FORCE_ACTIVE (default: 1 / True for Render)
    #   - When True: if lock acquisition fails, proceed as ACTIVE anyway
    #     (assumes only one Render Web Service instance)
    #   - When False: don't proceed if lock acquisition fails
    #
    # SINGLETON_LOCK_STRICT (default: 0)
    #   - When True: exit immediately if lock acquisition fails
    #   - When False: continue in PASSIVE mode if lock acquisition fails
    if cfg.database_url:
        try:
            from database import get_connection_pool

            get_connection_pool()
        except Exception as e:
            logger.warning("[DB] Could not initialize psycopg2 pool for lock: %s", e)

    lock = SingletonLock(cfg.database_url)
    lock_acquired = await lock.acquire()
    runtime_state.lock_acquired = lock_acquired

    active_state = ActiveState(active=bool(lock_acquired))
    if not active_state.active:
        logger.warning("[LOCK] Not acquired - starting in PASSIVE mode (will retry)")
    else:
        logger.info("[LOCK] Acquired - ACTIVE")

    db_service = None
    free_manager = None

    async def init_active_services() -> None:
        nonlocal db_service, free_manager

        if cfg.database_url:
            try:
                from app.database.services import DatabaseService
                from app.free.manager import FreeModelManager

                db_service = DatabaseService(cfg.database_url)
                await db_service.initialize()
                free_manager = FreeModelManager(db_service)

                from bot.handlers.balance import set_database_service as set_balance_db
                from bot.handlers.history import set_database_service as set_history_db
                from bot.handlers.marketing import (
                    set_database_service as set_marketing_db,
                    set_free_manager,
                )

                set_balance_db(db_service)
                set_history_db(db_service)
                set_marketing_db(db_service)
                set_free_manager(free_manager)

                logger.info("[DB] DatabaseService initialized and injected into handlers")
            except Exception as e:
                logger.warning("[DB] Database init skipped/failed: %s", e)
                db_service = None

        if effective_bot_mode == "webhook" and not cfg.dry_run:
            webhook_url = _build_webhook_url(cfg)
            if not webhook_url:
                raise RuntimeError("WEBHOOK_BASE_URL is required for BOT_MODE=webhook")

            from app.utils.webhook import ensure_webhook

            await ensure_webhook(
                bot,
                webhook_url=webhook_url,
                secret_token=cfg.webhook_secret_token or None,
            )

    runner: Optional[web.AppRunner] = None
    lock_task: Optional[asyncio.Task] = None
    passive_warning_shown = False  # Show warning only once when entering passive mode

    async def lock_watcher() -> None:
        """Rare lock acquisition retries with exponential backoff + jitter."""
        import random
        retry_count = 0
        
        while True:
            if active_state.active:
                return
            
            # Exponential backoff: 60s base + random jitter (0-30s)
            # On first retry: 60s, then 60s, then 60s... (fixed interval, no exponential)
            # This avoids thundering herd on rolling deploy
            wait_time = 60 + random.randint(0, 30)
            retry_count += 1
            
            logger.debug(f"[LOCK] Passive mode - retrying in {wait_time}s (attempt #{retry_count})")
            await asyncio.sleep(wait_time)
            
            got = await lock.acquire()
            if got:
                active_state.active = True
                runtime_state.lock_acquired = True
                logger.info("[LOCK] Acquired after retry - switching to ACTIVE")
                try:
                    await init_active_services()
                except Exception as e:
                    logger.exception("[ACTIVE] init failed after lock acquisition: %s", e)
                return

    try:
        if effective_bot_mode == "polling":
            app = _make_web_app(dp=dp, bot=bot, cfg=cfg, active_state=active_state)
            if cfg.port:
                runner = await _start_web_server(app, cfg.port)
                logger.info("[HEALTH] Server started on port %s", cfg.port)

            if not active_state.active:
                await asyncio.Event().wait()
                return

            await preflight_webhook(bot)
            await dp.start_polling(bot)
            return

        # webhook mode
        app = _make_web_app(dp=dp, bot=bot, cfg=cfg, active_state=active_state)
        if cfg.port:
            runner = await _start_web_server(app, cfg.port)
            logger.info("[HEALTH] Server started on port %s", cfg.port)

        if active_state.active:
            await init_active_services()
        else:
            lock_task = asyncio.create_task(lock_watcher())

        await asyncio.Event().wait()
    finally:
        try:
            if lock_task is not None:
                lock_task.cancel()
                with contextlib.suppress(Exception):
                    await lock_task
        except Exception:
            pass
        try:
            if runner is not None:
                await runner.cleanup()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        try:
            if db_service is not None:
                await db_service.close()
        except Exception:
            pass
        try:
            await lock.release()
        except Exception:
            pass

        # Close sync pool used by advisory lock (best-effort)
        try:
            from database import close_connection_pool

            close_connection_pool()
        except Exception:
            pass


if __name__ == "__main__":

    asyncio.run(main())
