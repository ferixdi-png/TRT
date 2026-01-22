#!/usr/bin/env python3
"""
Canonical Python entry point for KIE Telegram Bot.
Starts healthcheck server first, then launches the bot (polling or webhook).
Can be executed directly or invoked via the Node.js wrapper.
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logger = logging.getLogger("entrypoints.run_bot")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
    return default


def is_preflight_strict() -> bool:
    return _read_bool_env("BILLING_PREFLIGHT_STRICT", True)

def configure_logging() -> None:
    """Configure root logger if it was not configured earlier."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def resolve_port(default: int = 10000) -> int:
    """Resolve PORT for healthcheck server with a safe fallback."""
    raw_port = os.getenv("PORT", str(default)).strip()
    try:
        return int(raw_port)
    except ValueError:
        logger.warning("Invalid PORT value '%s', falling back to %s", raw_port, default)
        return default

ASYNC_HEALTHCHECK_HINT = (
    "Healthcheck server did not start (port may be busy or PORT not set). "
    "Render may consider the service unhealthy if nothing else binds the port."
)

async def get_webhook_handler():
    """Get webhook handler if bot is in webhook mode."""
    try:
        bot_mode = os.getenv("BOT_MODE", "").lower()
        if bot_mode != "webhook":
            return None
        
        # Import and return webhook handler from bot_kie
        from bot_kie import create_webhook_handler
        return await create_webhook_handler()
    except Exception as exc:
        logger.debug("Webhook handler not available: %s", exc)
        return None

async def start_healthcheck(port: int) -> bool:
    """Start the aiohttp healthcheck server; never raise on failure."""
    try:
        from app.utils.healthcheck import start_health_server
    except Exception as exc:  # ImportError or runtime issues
        logger.warning("Healthcheck module is unavailable: %s", exc, exc_info=True)
        return False

    try:
        webhook_handler = await get_webhook_handler()
        started = await start_health_server(port=port, webhook_handler=webhook_handler, self_check=True)
        if started:
            logger.info("Healthcheck server started on port %s", port)
        else:
            logger.warning(ASYNC_HEALTHCHECK_HINT)
        return bool(started)
    except Exception as exc:
        logger.warning("Failed to start healthcheck server: %s", exc, exc_info=True)
        logger.warning(ASYNC_HEALTHCHECK_HINT)
        return False

async def stop_healthcheck(started: bool) -> None:
    """Stop healthcheck server if it was started."""
    if not started:
        return
    try:
        from app.utils.healthcheck import stop_health_server
    except Exception as exc:
        logger.warning("Healthcheck module is unavailable during shutdown: %s", exc, exc_info=True)
        return

    try:
        await stop_health_server()
        logger.info("Healthcheck server stopped")
    except Exception as exc:
        logger.warning("Failed to stop healthcheck server: %s", exc, exc_info=True)

async def run_bot() -> None:
    """Run the Telegram bot using the existing async entrypoint."""
    from bot_kie import main as bot_main
    await bot_main()

async def main() -> None:
    """Start healthcheck first, then the Telegram bot."""
    configure_logging()
    port = resolve_port()
    logger.info("Python entrypoint starting: healthcheck -> bot")

    health_started = await start_healthcheck(port)

    from app.storage import get_storage
    from app.diagnostics.billing_preflight import (
        format_billing_preflight_report,
        run_billing_preflight,
    )

    storage = get_storage()
    db_ok = False
    try:
        if hasattr(storage, "ping") and asyncio.iscoroutinefunction(storage.ping):
            db_ok = await storage.ping()
        elif hasattr(storage, "test_connection"):
            db_ok = await asyncio.to_thread(storage.test_connection)
    except Exception as exc:
        logger.error("DB connectivity check failed: %s", exc, exc_info=True)
        db_ok = False

    if not db_ok:
        logger.error("DB connection failed, aborting startup before Telegram updates.")
        await stop_healthcheck(health_started)
        sys.exit(1)
    logger.info("DB connection OK, running billing preflight.")

    preflight_report = await run_billing_preflight(storage, db_pool=None)
    preflight_result = preflight_report.get("result")
    logger.info("Billing preflight result: %s", preflight_result)
    if preflight_result == "FAIL":
        logger.error("Billing preflight failed: %s", format_billing_preflight_report(preflight_report))
        how_to_fix = preflight_report.get("how_to_fix") or []
        if how_to_fix:
            logger.error("Billing preflight suggested fixes: %s", "; ".join(how_to_fix))
        if is_preflight_strict():
            logger.error("Billing preflight strict mode enabled; aborting startup before Telegram updates.")
            await stop_healthcheck(health_started)
            sys.exit(1)
        logger.warning("Billing preflight strict mode disabled; continuing startup.")

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, shutdown_event.set)

    bot_task = asyncio.create_task(run_bot(), name="bot-main")
    stop_task = asyncio.create_task(shutdown_event.wait(), name="shutdown-event")

    done, pending = await asyncio.wait(
        {bot_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_task in done and not bot_task.done():
        logger.info("Shutdown signal received, stopping bot task...")
        bot_task.cancel()
        with suppress(asyncio.CancelledError):
            await bot_task
    elif bot_task in done:
        exc = bot_task.exception()
        if exc:
            logger.error("Bot task failed: %s", exc, exc_info=True)
            raise exc

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    await stop_healthcheck(health_started)


def run() -> None:
    """Synchronous wrapper for running via __main__."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested (KeyboardInterrupt)")
    except Exception as exc:
        logger.error("Fatal error in entrypoint: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
