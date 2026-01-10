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

    return Bot, Dispatcher, MemoryStorage, Update


Bot, Dispatcher, MemoryStorage, Update = _import_real_aiogram_symbols()

from app.utils.logging_config import setup_logging  # noqa: E402
from app.utils.runtime_state import runtime_state  # noqa: E402


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
    port = int(os.getenv("PORT", "10000"))
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/")
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
        if not self.database_url:
            self._acquired = True
            return True
        try:
            from app.locking.single_instance import acquire_single_instance_lock

            self._acquired = acquire_single_instance_lock(self.database_url, lock_key=self.key)
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

            release_single_instance_lock(self.database_url, lock_key=self.key)
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

    bot = Bot(token=token, parse_mode="HTML")
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

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def root(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def webhook(request: web.Request) -> web.Response:
        secret = request.match_info.get("secret")
        if secret != cfg.webhook_secret_path:
            # Hide existence
            raise web.HTTPNotFound()

        # Enforce Telegram header secret if configured
        if cfg.webhook_secret_token:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != cfg.webhook_secret_token:
                raise web.HTTPUnauthorized()

        if not active_state.active:
            # During rolling deploy, we may start PASSIVE. Returning 503 forces Telegram
            # to retry until this instance becomes ACTIVE (lock acquired).
            raise web.HTTPServiceUnavailable()

        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="bad json")

        try:
            update = Update.model_validate(payload)
            await dp.feed_update(bot, update)
        except Exception as e:
            logger.exception("[WEBHOOK] Failed to process update: %s", e)
            # 200 to prevent Telegram storm; errors are logged.
            return web.Response(status=200, text="ok")

        return web.Response(status=200, text="ok")

    app.router.add_get("/health", health)
    app.router.add_get("/", root)
    app.router.add_head("/", root)
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
    runtime_state.bot_mode = cfg.bot_mode
    runtime_state.last_start_time = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("STARTUP (aiogram)")
    logger.info("BOT_MODE=%s PORT=%s", cfg.bot_mode, cfg.port)
    logger.info("WEBHOOK_BASE_URL=%s", cfg.webhook_base_url or "(not set)")
    logger.info("WEBHOOK_SECRET_PATH=%s", (cfg.webhook_secret_path[:6] + "..."))
    logger.info("WEBHOOK_SECRET_TOKEN=%s", "SET" if cfg.webhook_secret_token else "(not set)")
    logger.info("DRY_RUN=%s", cfg.dry_run)
    logger.info("=" * 60)

    dp, bot = create_bot_application()

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

        if not cfg.dry_run:
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

    async def lock_watcher() -> None:
        """Retry lock acquisition after rolling deploy and flip ACTIVE without restart."""
        while True:
            if active_state.active:
                return
            await asyncio.sleep(5)
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
        if cfg.bot_mode == "polling":
            if not active_state.active:
                # In polling mode we cannot bind the port-less worker on Render reliably.
                # Keep process alive (health-only is not used here).
                await asyncio.Event().wait()
                return

            await preflight_webhook(bot)
            await dp.start_polling(bot)
            return

        # webhook mode
        app = _make_web_app(dp=dp, bot=bot, cfg=cfg, active_state=active_state)
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


if __name__ == "__main__":

    asyncio.run(main())
