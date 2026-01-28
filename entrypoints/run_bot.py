#!/usr/bin/env python3
"""
Canonical Python entry point for KIE Telegram Bot.
Starts healthcheck server first, then launches the bot (polling or webhook).
Can be executed directly or invoked via the Node.js wrapper.
"""

import asyncio
import inspect
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

def is_storage_preflight_strict() -> bool:
    return _read_bool_env("STORAGE_PREFLIGHT_STRICT", True)

def is_boot_diagnostics_strict() -> bool:
    return _read_bool_env("BOOT_DIAGNOSTICS_STRICT", False)

def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
        return default

def _read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value.strip())
    except ValueError:
        logger.warning("Invalid %s value '%s', defaulting to %s", name, raw_value, default)
        return default

async def _check_storage_connectivity(storage) -> bool:
    if storage is None:
        return False
    if hasattr(storage, "ping") and inspect.iscoroutinefunction(storage.ping):
        return await storage.ping()
    if hasattr(storage, "test_connection"):
        return await asyncio.to_thread(storage.test_connection)
    return True

async def _wait_for_storage(storage) -> bool:
    retries = max(0, _read_int_env("DB_STARTUP_RETRIES", 2))
    base_delay = max(0.0, _read_float_env("DB_STARTUP_RETRY_DELAY", 1.5))
    attempt = 0
    while True:
        attempt += 1
        db_ok = await _check_storage_connectivity(storage)
        if db_ok:
            return True
        if attempt > retries:
            return False
        delay = base_delay * (2 ** (attempt - 1))
        logger.warning("DB connectivity check failed, retrying in %.1fs (attempt %s/%s)", delay, attempt, retries + 1)
        await asyncio.sleep(delay)

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

async def _safe_async_cleanup(
    loop: asyncio.AbstractEventLoop,
    action: str,
    coro,
) -> None:
    if loop.is_closed():
        logger.info("shutdown_skip reason=loop_closed action=%s", action)
        return
    try:
        await coro
    except Exception as exc:
        logger.warning("shutdown_failed action=%s error=%s", action, exc, exc_info=True)


async def run_bot_preflight() -> None:
    """Async preflight: healthcheck, storage, diagnostics, bot initialization."""
    configure_logging()
    port = resolve_port()
    logger.info("Python entrypoint starting preflight for webhook mode")

    # P0 FIX: В webhook режиме не стартуем healthcheck чтобы избежать конфликта портов
    bot_mode = os.getenv("BOT_MODE", "").lower().strip()
    if bot_mode == "webhook":
        logger.info("Webhook mode detected: skipping healthcheck server to avoid port conflicts")
        health_started = False
    else:
        logger.info("Polling mode detected: starting healthcheck server")
        health_started = await start_healthcheck(port)

    loop = asyncio.get_running_loop()
    storage = None

    try:
        from app.storage import get_storage
        from app.diagnostics.billing_preflight import (
            format_billing_preflight_report,
            run_billing_preflight,
        )
        from app.diagnostics.boot import log_boot_report, run_boot_diagnostics

        storage = get_storage()
        db_ok = False
        try:
            db_ok = await _wait_for_storage(storage)
        except Exception as exc:
            logger.error("DB connectivity check failed: %s", exc, exc_info=True)
            db_ok = False

        if not db_ok:
            if is_storage_preflight_strict():
                logger.error("DB connection failed, aborting startup before Telegram updates.")
                await stop_healthcheck(health_started)
                sys.exit(1)
            logger.warning("DB connection failed, continuing startup in degraded mode.")
        else:
            logger.info("DB connection OK, running billing preflight.")

        boot_timeout = _read_float_env("BOOT_DIAGNOSTICS_TIMEOUT_SECONDS", 5.0)
        try:
            boot_report = await asyncio.wait_for(
                run_boot_diagnostics(os.environ, storage=storage, redis_client=None),
                timeout=boot_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("BOOT_DIAGNOSTICS_TIMEOUT timeout_s=%s", boot_timeout)
            boot_report = {
                "meta": {"bot_mode": os.getenv("BOT_MODE", ""), "port": port},
                "summary": {},
                "result": "DEGRADED",
            }
        log_boot_report(boot_report)
        if boot_report.get("result") == "FAIL":
            logger.error("Boot diagnostics reported FAIL.")
            if is_boot_diagnostics_strict():
                logger.error("Boot diagnostics strict mode enabled; aborting startup before Telegram updates.")
                await stop_healthcheck(health_started)
                sys.exit(1)
            logger.warning("Boot diagnostics strict mode disabled; continuing startup.")

        if db_ok:
            preflight_timeout = _read_float_env("BILLING_PREFLIGHT_TIMEOUT_SECONDS", 6.0)
            try:
                preflight_report = await asyncio.wait_for(
                    run_billing_preflight(storage, db_pool=None),
                    timeout=preflight_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("BILLING_PREFLIGHT_TIMEOUT timeout_s=%s", preflight_timeout)
                preflight_report = {"result": "DEGRADED", "how_to_fix": ["Preflight timeout"], "sections": {}}
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
        else:
            logger.warning("Billing preflight skipped due to failed DB connectivity.")

        # Инициализация бота (без запуска webhook)
        import importlib.util
        bot_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_kie.py")
        spec = importlib.util.spec_from_file_location("bot_kie_main", bot_file_path)
        bot_kie_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bot_kie_module)
        
        # Запускаем main() для инициализации, но не для webhook
        await bot_kie_module.main()
        
        # Возвращаем application для webhook запуска
        return bot_kie_module.application

    finally:
        await _safe_async_cleanup(loop, "healthcheck_stop", stop_healthcheck(health_started))
        if storage is not None and hasattr(storage, "close"):
            close_fn = storage.close
            if inspect.iscoroutinefunction(close_fn):
                await _safe_async_cleanup(loop, "storage_close", close_fn())
            else:
                if loop.is_closed():
                    logger.info("shutdown_skip reason=loop_closed action=storage_close")
                else:
                    try:
                        close_fn()
                    except Exception as exc:
                        logger.warning("shutdown_failed action=storage_close error=%s", exc, exc_info=True)


async def run_bot() -> None:
    """Run the Telegram bot using the existing async entrypoint."""
    # Используем абсолютный импорт с указанием полного пути
    import importlib.util
    import os
    
    # Полный путь к основному файлу бота
    bot_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_kie.py")
    
    # Загружаем модуль динамически
    spec = importlib.util.spec_from_file_location("bot_kie_main", bot_file_path)
    bot_kie_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot_kie_module)
    
    # Получаем функцию main
    bot_main = bot_kie_module.main
    await bot_main()

async def main() -> None:
    """Start healthcheck first, then the Telegram bot."""
    configure_logging()
    port = resolve_port()
    logger.info("Python entrypoint starting: healthcheck -> bot")

    # P0 FIX: В webhook режиме не стартуем healthcheck чтобы избежать конфликта портов
    bot_mode = os.getenv("BOT_MODE", "").lower().strip()
    if bot_mode == "webhook":
        logger.info("Webhook mode detected: skipping healthcheck server to avoid port conflicts")
        health_started = False
    else:
        logger.info("Polling mode detected: starting healthcheck server")
        health_started = await start_healthcheck(port)

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    bot_task = None
    stop_task = None
    storage = None
    stopping = False

    try:
        from app.storage import get_storage
        from app.diagnostics.billing_preflight import (
            format_billing_preflight_report,
            run_billing_preflight,
        )
        from app.diagnostics.boot import log_boot_report, run_boot_diagnostics

        storage = get_storage()
        db_ok = False
        try:
            db_ok = await _wait_for_storage(storage)
        except Exception as exc:
            logger.error("DB connectivity check failed: %s", exc, exc_info=True)
            db_ok = False

        if not db_ok:
            if is_storage_preflight_strict():
                logger.error("DB connection failed, aborting startup before Telegram updates.")
                await stop_healthcheck(health_started)
                sys.exit(1)
            logger.warning("DB connection failed, continuing startup in degraded mode.")
        else:
            logger.info("DB connection OK, running billing preflight.")

        boot_timeout = _read_float_env("BOOT_DIAGNOSTICS_TIMEOUT_SECONDS", 5.0)
        try:
            boot_report = await asyncio.wait_for(
                run_boot_diagnostics(os.environ, storage=storage, redis_client=None),
                timeout=boot_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("BOOT_DIAGNOSTICS_TIMEOUT timeout_s=%s", boot_timeout)
            boot_report = {
                "meta": {"bot_mode": os.getenv("BOT_MODE", ""), "port": port},
                "summary": {},
                "result": "DEGRADED",
            }
        log_boot_report(boot_report)
        if boot_report.get("result") == "FAIL":
            logger.error("Boot diagnostics reported FAIL.")
            if is_boot_diagnostics_strict():
                logger.error("Boot diagnostics strict mode enabled; aborting startup before Telegram updates.")
                await stop_healthcheck(health_started)
                sys.exit(1)
            logger.warning("Boot diagnostics strict mode disabled; continuing startup.")

        if db_ok:
            preflight_timeout = _read_float_env("BILLING_PREFLIGHT_TIMEOUT_SECONDS", 6.0)
            try:
                preflight_report = await asyncio.wait_for(
                    run_billing_preflight(storage, db_pool=None),
                    timeout=preflight_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("BILLING_PREFLIGHT_TIMEOUT timeout_s=%s", preflight_timeout)
                preflight_report = {"result": "DEGRADED", "how_to_fix": ["Preflight timeout"], "sections": {}}
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
        else:
            logger.warning("Billing preflight skipped due to failed DB connectivity.")

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
            stopping = True
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
    except asyncio.CancelledError:
        stopping = True
        logger.info("Shutdown requested (CancelledError)")
        if bot_task and not bot_task.done():
            bot_task.cancel()
            with suppress(asyncio.CancelledError):
                await bot_task
    finally:
        if stop_task and not stop_task.done():
            stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task
        if bot_task and not bot_task.done():
            bot_task.cancel()
            with suppress(asyncio.CancelledError):
                await bot_task

        await _safe_async_cleanup(loop, "healthcheck_stop", stop_healthcheck(health_started))

        if storage is not None and hasattr(storage, "close"):
            close_fn = storage.close
            if inspect.iscoroutinefunction(close_fn):
                await _safe_async_cleanup(loop, "storage_close", close_fn())
            else:
                if loop.is_closed():
                    logger.info("shutdown_skip reason=loop_closed action=storage_close")
                else:
                    try:
                        close_fn()
                    except Exception as exc:
                        logger.warning("shutdown_failed action=storage_close error=%s", exc, exc_info=True)

        try:
            from app.utils.singleton_lock import release_singleton_lock
        except Exception as exc:
            logger.warning("shutdown_failed action=singleton_lock_import error=%s", exc, exc_info=True)
        else:
            await _safe_async_cleanup(loop, "singleton_lock_release", release_singleton_lock())
        if stopping:
            logger.info("Shutdown complete.")


def run() -> None:
    """Synchronous wrapper for running via __main__."""
    try:
        # P0 FIX: Для webhook режима делаем preflight через asyncio.run(), затем sync webhook
        bot_mode = os.getenv("BOT_MODE", "").lower().strip()
        if bot_mode == "webhook":
            logger.info("Webhook mode detected: running preflight then sync webhook")
            import asyncio
            
            # Шаг 1: Выполняем async preflight (healthcheck, storage, diagnostics, bot init)
            logger.info("Step 1: Running async preflight...")
            application = asyncio.run(run_bot_preflight())
            
            # Cleanup background tasks после preflight чтобы предотвратить GatheringFuture exceptions
            import bot_kie
            if hasattr(bot_kie, '_background_tasks') and bot_kie._background_tasks:
                logger.info(f"Cleaning up {len(bot_kie._background_tasks)} background tasks after preflight")
                import asyncio
                
                def handle_asyncio_exception(loop, context):
                    """Глобальный handler для asyncio exceptions"""
                    msg = context.get("message", "Unknown asyncio error")
                    exception = context.get("exception")
                    if exception and "CancelledError" in str(type(exception)):
                        # Игнорируем CancelledError - это штатная ситуация
                        logger.debug(f"Ignoring CancelledError in asyncio: {msg}")
                        return
                    logger.error(f"Asyncio error: {msg}", exc_info=exception)
                
                # Создаем временный loop для cleanup
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.set_exception_handler(handle_asyncio_exception)
                try:
                    # Отменяем все задачи
                    for task in list(bot_kie._background_tasks):
                        if not task.done():
                            task.cancel()
                    # Собираем отменённые задачи
                    if bot_kie._background_tasks:
                        loop.run_until_complete(asyncio.gather(*bot_kie._background_tasks, return_exceptions=True))
                    bot_kie._background_tasks.clear()
                except Exception as e:
                    logger.warning(f"Error during background tasks cleanup: {e}")
                finally:
                    loop.close()
            
            # Шаг 2: Запускаем webhook в sync режиме - PTB сам управляет loop
            logger.info("Step 2: Starting webhook in sync mode...")
            from bot_kie import run_webhook_sync
            run_webhook_sync(application)
            
        else:
            # Для polling режима оставляем как было
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested (KeyboardInterrupt)")
    except asyncio.CancelledError:
        logger.info("Shutdown requested (CancelledError)")
    except Exception as exc:
        logger.error("Fatal error in entrypoint: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
