#!/usr/bin/env python3
"""
Main entry point for Telegram Bot
Render-optimized entrypoint
"""

import sys
import os
import logging
import asyncio
import inspect
import time
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настраиваем унифицированное логирование ПЕРЕД импортом других модулей
from app.utils.logging_config import setup_logging, get_logger

LOG_LEVEL_ENV = os.getenv("LOG_LEVEL", "").upper()
setup_logging(level=(logging.DEBUG if LOG_LEVEL_ENV == "DEBUG" else logging.INFO))
logger = get_logger(__name__)

# Глобальные переменные для observability
_start_time = time.time()
_application: Optional[object] = None


def ensure_data_directory(data_dir: str) -> bool:
    """
    Гарантирует создание data директории и проверяет права записи.

    Returns:
        True если директория доступна для записи, False иначе
    """
    try:
        data_path = Path(data_dir)
        data_path.mkdir(parents=True, exist_ok=True)

        # Проверяем права записи
        test_file = data_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            logger.info(f"[OK] Data directory writable: {data_dir}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] Cannot write to data directory {data_dir}: {e}")
            return False
    except Exception as e:
        logger.error(f"[FAIL] Cannot create data directory {data_dir}: {e}")
        return False


def load_settings():
    """Загружает и валидирует настройки из ENV"""
    from app.config import get_settings
    from app.utils.startup_validation import startup_validation

    logger.info("=" * 60)
    logger.info("BOT STARTING")
    logger.info("=" * 60)

    try:
        # Валидируем обязательные ENV переменные
        startup_validation()

        # Валидируем настройки при загрузке
        settings = get_settings(validate=True)

        # Startup banner
        logger.info("=" * 60)
        logger.info("STARTUP BANNER")
        logger.info("=" * 60)
        logger.info(f"Python version: {sys.version.split()[0]}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Process ID: {os.getpid()}")
        logger.info(f"Render environment: {os.getenv('RENDER', 'not detected')}")
        logger.info(f"Storage mode: {settings.get_storage_mode()}")
        logger.info(f"KIE mode: {'stub' if os.getenv('KIE_STUB') else 'real'}")
        logger.info(f"DATABASE_URL: {'[SET]' if settings.database_url else '[NOT SET]'}")
        logger.info(f"Data directory: {settings.data_dir}")
        logger.info("=" * 60)

        # Проверяем data directory
        if not ensure_data_directory(settings.data_dir):
            logger.error("[FAIL] Data directory not writable, exiting")
            sys.exit(1)

        # Проверяем каталог моделей при старте
        try:
            # Импортируем функцию проверки напрямую
            from pathlib import Path

            verify_script = Path(__file__).parent.parent / "scripts" / "verify_catalog.py"
            if verify_script.exists():
                # Добавляем scripts в путь для импорта
                scripts_dir = str(verify_script.parent)
                if scripts_dir not in sys.path:
                    sys.path.insert(0, scripts_dir)

                # Импортируем функцию verify_catalog
                import importlib.util

                spec = importlib.util.spec_from_file_location("verify_catalog", verify_script)
                verify_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(verify_module)

                logger.info("=" * 60)
                logger.info("CATALOG VERIFICATION")
                logger.info("=" * 60)
                if not verify_module.verify_catalog():
                    logger.error("[FAIL] Catalog verification failed, exiting")
                    sys.exit(1)
                logger.info("[OK] Catalog verification passed")
        except ImportError as e:
            logger.warning(f"[WARN] Could not import catalog verification: {e}")
            # Не останавливаем бота, только предупреждаем
        except Exception as e:
            logger.warning(f"[WARN] Catalog verification error: {e}")
            # Не останавливаем бота, только предупреждаем

        return settings
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace

        log_error_with_stacktrace(logger, e, "Failed to load settings")
        sys.exit(1)


async def build_application(settings):
    """Создает и настраивает Telegram Application"""
    global _application

    try:
        from bot_kie import create_bot_application

        logger.info("[BUILD] Creating Telegram Application...")
        _application = await create_bot_application(settings)
        logger.info("[BUILD] Application created successfully")

        return _application
    except (AttributeError, NameError):
        logger.warning("[BUILD] create_bot_application not found, using legacy initialization")
        return None
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace

        log_error_with_stacktrace(logger, e, "Failed to build application")
        raise


async def start_health_server(port: int, **kwargs) -> bool:
    """Запускает healthcheck сервер в том же event loop"""
    try:
        from app.utils.healthcheck import start_health_server

        return await start_health_server(port=port, **kwargs)
    except Exception as e:
        logger.warning(f"[HEALTH] Failed to start health server: {e}")
        return False


async def run(settings, application):
    """Запускает бота (polling или webhook) или переходит в passive mode"""
    global _application

    # Singleton lock должен быть получен ДО любых async операций
    from app.locking.single_instance import (
        acquire_single_instance_lock,
        release_single_instance_lock,
    )

    # NOTE:
    # Advisory lock historically existed to prevent Telegram 409 conflicts in POLLING mode.
    # In WEBHOOK mode, disabling webhook handling causes 404 storms during rolling deploy.
    bot_mode = (getattr(settings, "bot_mode", None) or os.getenv("BOT_MODE", "polling")).lower()

    lock_acquired = acquire_single_instance_lock()

    if not lock_acquired and bot_mode == "polling":
        # PASSIVE MODE: lock не получен в polling режиме — запускаем только healthcheck
        logger.warning("=" * 60)
        logger.warning("[PASSIVE MODE] Singleton lock not acquired")
        logger.warning("[PASSIVE MODE] Telegram runner disabled (polling)")
        logger.warning("[PASSIVE MODE] Healthcheck server only")
        logger.warning("=" * 60)

        # Запускаем healthcheck сервер (если PORT задан)
        if settings.port:
            logger.info(f"[PASSIVE] Starting healthcheck server on port {settings.port}")
            await start_health_server(port=settings.port)

            # Держим процесс живым для healthcheck
            logger.info("[PASSIVE] Healthcheck server running, keeping process alive...")
            try:
                # Бесконечный цикл для поддержания healthcheck
                while True:
                    await asyncio.sleep(60)  # Проверяем каждую минуту
            except KeyboardInterrupt:
                logger.info("[PASSIVE] Shutting down healthcheck server")
        else:
            logger.warning("[PASSIVE] PORT not set, cannot start healthcheck server")
            logger.warning("[PASSIVE] Exiting (no work to do)")

        return

    if not lock_acquired and bot_mode == "webhook":
        logger.warning(
            "[LOCK] PostgreSQL advisory lock not acquired, but continuing in WEBHOOK mode "
            "to avoid 404 on Telegram updates (zero-downtime deploy handover)."
        )

    try:
        # Запускаем healthcheck сервер (если PORT задан)
        if settings.port:
            settings_bot_mode = getattr(
                settings, "bot_mode", os.getenv("BOT_MODE", "polling").lower()
            )
            webhook_secret_path = getattr(settings, "webhook_secret_path", "")
            webhook_secret_token = getattr(settings, "webhook_secret_token", "")
            if settings_bot_mode == "webhook" and application and webhook_secret_path:
                await start_health_server(
                    port=settings.port,
                    application=application,
                    webhook_secret_path=webhook_secret_path,
                    webhook_secret_token=webhook_secret_token,
                )
            else:
                await start_health_server(port=settings.port)

        if application is None:
            # Используем старый способ через bot_kie.main()
            logger.info("[RUN] Using legacy bot_kie.main() initialization")
            from bot_kie import main as bot_main

            await bot_main()
        else:
            # Используем новый способ
            logger.info("[RUN] Initializing application...")
            await application.initialize()
            await application.start()

            logger.info("=" * 60)
            logger.info("BOT READY")
            logger.info("=" * 60)
            logger.info("Handlers registered and application started")

            # Определяем режим работы бота
            bot_mode = os.getenv("BOT_MODE", "").lower().strip()

            # AUTO режим: определяем автоматически если не задан
            if not bot_mode or bot_mode == "auto":
                # Логика AUTO:
                # - Если RENDER=true и PORT задан -> поднимать healthcheck web
                # - Telegram runner (polling/webhook) включать только если:
                #   * TELEGRAM_BOT_TOKEN задан
                #   * SINGLETON_LOCK получен
                # - Если lock не получен -> passive mode
                is_render = os.getenv("RENDER", "").lower() in ("1", "true", "yes")
                has_port = settings.port and settings.port > 0
                has_token = bool(settings.telegram_bot_token)

                if has_token and lock_acquired:
                    # Есть токен и lock получен -> polling
                    bot_mode = "polling"
                    logger.info("[AUTO] BOT_MODE=auto -> polling (token present, lock acquired)")
                elif is_render and has_port:
                    # Render с PORT -> passive mode (healthcheck only)
                    bot_mode = "passive"
                    logger.info(
                        "[AUTO] BOT_MODE=auto -> passive (Render with PORT, no token or lock)"
                    )
                else:
                    # По умолчанию passive
                    bot_mode = "passive"
                    logger.info(
                        f"[AUTO] BOT_MODE=auto -> passive (token={has_token}, lock={lock_acquired}, render={is_render}, port={has_port})"
                    )
            else:
                # Явно заданный режим
                logger.info(f"[BOT_MODE] Using explicit mode: {bot_mode}")

            # Запускаем polling или webhook
            if bot_mode == "webhook":
                webhook_url = getattr(settings, "webhook_url", "")
                webhook_secret_path = getattr(settings, "webhook_secret_path", "")
                webhook_secret_token = getattr(settings, "webhook_secret_token", "")
                if not webhook_url:
                    logger.error("[FAIL] WEBHOOK_BASE_URL not set for webhook mode")
                    sys.exit(1)
                if getattr(settings, "test_mode", False) or getattr(settings, "dry_run", False):
                    from app.utils.webhook import mask_webhook_url

                    logger.info(
                        "[RUN] TEST_MODE/DRY_RUN enabled; skipping webhook set for %s",
                        mask_webhook_url(webhook_url, webhook_secret_path),
                    )
                else:
                    from app.utils.webhook import ensure_webhook

                    get_webhook_info = getattr(application.bot, "get_webhook_info", None)
                    if not callable(get_webhook_info) or not inspect.iscoroutinefunction(
                        get_webhook_info
                    ):
                        if webhook_secret_token:
                            await application.bot.set_webhook(
                                webhook_url,
                                secret_token=webhook_secret_token,
                            )
                        else:
                            await application.bot.set_webhook(webhook_url)
                    else:
                        await ensure_webhook(
                            application.bot,
                            webhook_url,
                            secret_token=webhook_secret_token,
                        )
                logger.info("[RUN] Webhook mode - bot is ready")
            else:
                # Polling mode - безопасный запуск с обработкой конфликтов
                logger.info("[RUN] Starting polling...")

                # КРИТИЧНО: Задержка перед запуском polling для предотвращения конфликтов
                logger.info("[RUN] Waiting 15 seconds to avoid conflicts with previous instance...")
                await asyncio.sleep(15)

                # КРИТИЧНО: Удаляем webhook ПЕРЕД запуском polling
                try:
                    await application.bot.delete_webhook(drop_pending_updates=True)
                    webhook_info = await application.bot.get_webhook_info()
                    if webhook_info.url:
                        from app.utils.webhook import mask_webhook_url

                        logger.warning(
                            "[RUN] Webhook still present: %s",
                            mask_webhook_url(webhook_info.url, settings.webhook_secret_path),
                        )
                    else:
                        logger.info("[RUN] Webhook removed successfully")
                except Exception as e:
                    logger.warning(f"[RUN] Error removing webhook: {e}")
                    # Проверяем на конфликт
                    from telegram.error import Conflict

                    if isinstance(e, Conflict) or "Conflict" in str(e) or "409" in str(e):
                        logger.error("[RUN] Conflict detected while removing webhook - exiting")
                        from app.bot_mode import handle_conflict_gracefully

                        handle_conflict_gracefully(
                            e if isinstance(e, Conflict) else Conflict(str(e)), "polling"
                        )
                        return

                # КРИТИЧНО: Добавляем обработчик ошибок для updater через post_init
                async def handle_updater_error(update, context):
                    """Обработчик ошибок для updater polling loop"""
                    error = context.error
                    error_msg = str(error) if error else ""

                    from telegram.error import Conflict

                    if (
                        isinstance(error, Conflict)
                        or "Conflict" in error_msg
                        or "terminated by other getUpdates" in error_msg
                        or "409" in error_msg
                    ):
                        logger.error(f"[UPDATER] 409 CONFLICT in updater loop: {error_msg}")
                        logger.error("[UPDATER] Stopping updater and exiting...")

                        # Останавливаем updater немедленно
                        try:
                            if application.updater and application.updater.running:
                                await application.updater.stop()
                                logger.info("[UPDATER] Updater stopped")
                        except Exception as e:
                            logger.warning(f"[UPDATER] Error stopping updater: {e}")

                        # Останавливаем application
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass

                        # Освобождаем lock и выходим
                        try:
                            from app.locking.single_instance import release_single_instance_lock

                            release_single_instance_lock()
                        except:
                            pass

                        from app.bot_mode import handle_conflict_gracefully

                        handle_conflict_gracefully(
                            error if isinstance(error, Conflict) else Conflict(error_msg), "polling"
                        )
                        os._exit(0)

                # Добавляем обработчик ошибок для updater
                application.add_error_handler(handle_updater_error)

                # КРИТИЧНО: Проверяем конфликт ПЕРЕД запуском polling
                logger.info("[RUN] Checking for conflicts before polling start...")
                try:
                    # Пытаемся сделать тестовый getUpdates для проверки конфликта
                    await application.bot.get_updates(limit=1, timeout=1)
                    logger.info("[RUN] Pre-flight check passed: no conflicts detected")
                except Exception as test_e:
                    from telegram.error import Conflict

                    error_msg = str(test_e)
                    if (
                        isinstance(test_e, Conflict)
                        or "Conflict" in error_msg
                        or "409" in error_msg
                        or "terminated by other getUpdates" in error_msg
                    ):
                        logger.error(
                            f"[RUN] ❌❌❌ CONFLICT DETECTED in pre-flight check: {error_msg}"
                        )
                        logger.error("[RUN] Another bot instance is already polling - exiting")
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass
                        from app.bot_mode import handle_conflict_gracefully

                        handle_conflict_gracefully(
                            test_e if isinstance(test_e, Conflict) else Conflict(error_msg),
                            "polling",
                        )
                        return
                    else:
                        logger.warning(f"[RUN] Pre-flight check warning (non-conflict): {test_e}")

                # КРИТИЧНО: Запускаем polling с обработкой конфликтов
                # start_polling не блокирует - он запускает polling в фоне
                # Ошибки в updater loop обрабатываются через error handler
                try:
                    await application.updater.start_polling(drop_pending_updates=True)
                    logger.info("[RUN] Polling started successfully")
                except Exception as e:
                    from telegram.error import Conflict

                    error_msg = str(e)
                    if (
                        isinstance(e, Conflict)
                        or "Conflict" in error_msg
                        or "409" in error_msg
                        or "terminated by other getUpdates" in error_msg
                    ):
                        logger.error(
                            f"[RUN] ❌❌❌ CONFLICT DETECTED during polling start: {error_msg}"
                        )
                        logger.error("[RUN] Stopping updater and exiting immediately...")

                        # Останавливаем updater немедленно
                        try:
                            if application.updater and application.updater.running:
                                await application.updater.stop()
                                logger.info("[RUN] Updater stopped")
                        except Exception as stop_e:
                            logger.warning(f"[RUN] Error stopping updater: {stop_e}")

                        # Останавливаем application
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass

                        # Освобождаем lock
                        try:
                            from app.locking.single_instance import release_single_instance_lock

                            release_single_instance_lock()
                        except:
                            pass

                        from app.bot_mode import handle_conflict_gracefully

                        handle_conflict_gracefully(
                            e if isinstance(e, Conflict) else Conflict(error_msg), "polling"
                        )
                        os._exit(0)  # Немедленный выход
                    else:
                        raise  # Re-raise non-Conflict errors

                # КРИТИЧНО: НЕ мониторим updater через get_updates!
                # Это вызывает конфликты, потому что updater уже делает get_updates в своем loop.
                # Ошибки обрабатываются через error handler, который уже добавлен выше.

            # Ждем остановки
            try:
                if os.getenv("PYTEST_CURRENT_TEST"):
                    return
                await asyncio.Event().wait()  # Ждем бесконечно
            except KeyboardInterrupt:
                logger.info("[STOP] Bot stopped by user")
            finally:
                stop = getattr(application, "stop", None)
                if stop:
                    if inspect.iscoroutinefunction(stop):
                        await stop()
                    else:
                        stop()
                shutdown = getattr(application, "shutdown", None)
                if shutdown:
                    if inspect.iscoroutinefunction(shutdown):
                        await shutdown()
                    else:
                        shutdown()
    except KeyboardInterrupt:
        logger.info("[STOP] Bot stopped by user")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace

        log_error_with_stacktrace(logger, e, "Fatal error during bot run")
        logger.error("[FAIL] Bot failed to run. Check logs above for details.")
        sys.exit(1)
    finally:
        # Останавливаем healthcheck сервер
        from app.utils.healthcheck import stop_health_server

        await stop_health_server()

        # Закрываем пул БД при завершении
        try:
            from database import close_connection_pool

            close_connection_pool()
        except Exception:
            pass

            close_connection_pool()
        except Exception:
            pass

        # Освобождаем singleton lock
        release_single_instance_lock()


async def main():
    """Главная async функция"""
    try:
        # 1. Загружаем настройки
        settings = load_settings()

        # 2. Создаем application
        application = await build_application(settings)

        # 3. Запускаем бота
        await run(settings, application)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace

        log_error_with_stacktrace(logger, e, "Fatal error in main")
        sys.exit(1)


if __name__ == "__main__":
    # Запускаем async main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[STOP] Bot stopped by user")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace

        log_error_with_stacktrace(logger, e, "Fatal error in asyncio.run")
        sys.exit(1)
