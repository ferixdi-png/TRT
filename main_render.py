#!/usr/bin/env python3
"""
Render-first entrypoint для Telegram Bot
Единая точка входа для запуска на Render.com (Web Service или Worker)
"""

import sys
import os
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

# Настраиваем логирование ПЕРЕД импортом других модулей
from app.utils.logging_config import setup_logging, get_logger

setup_logging(level=logging.INFO)
logger = get_logger(__name__)

# Глобальные переменные
_start_time = time.time()
_application: Optional[object] = None


def log_env_snapshot():
    """Логирует snapshot ENV переменных без секретов"""
    env_vars = {
        "PORT": os.getenv("PORT", "not set"),
        "RENDER": os.getenv("RENDER", "not set"),
        "ENV": os.getenv("ENV", "not set"),
        "BOT_MODE": os.getenv("BOT_MODE", "not set"),
        "STORAGE_MODE": os.getenv("STORAGE_MODE", "not set"),
        "DATABASE_URL": "[SET]" if os.getenv("DATABASE_URL") else "[NOT SET]",
        "TELEGRAM_BOT_TOKEN": "[SET]" if os.getenv("TELEGRAM_BOT_TOKEN") else "[NOT SET]",
        "KIE_API_KEY": "[SET]" if os.getenv("KIE_API_KEY") else "[NOT SET]",
        "KIE_API_URL": os.getenv("KIE_API_URL", "not set"),
        "TEST_MODE": os.getenv("TEST_MODE", "not set"),
        "DRY_RUN": os.getenv("DRY_RUN", "not set"),
        "ALLOW_REAL_GENERATION": os.getenv("ALLOW_REAL_GENERATION", "not set"),
    }
    
    logger.info("=" * 60)
    logger.info("ENVIRONMENT VARIABLES SNAPSHOT")
    logger.info("=" * 60)
    for key, value in sorted(env_vars.items()):
        logger.info(f"{key}={value}")
    logger.info("=" * 60)


def ensure_data_directory(data_dir: str) -> bool:
    """Гарантирует создание data директории и проверяет права записи"""
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


def load_and_validate_settings():
    """Загружает и валидирует настройки из ENV"""
    from app.config import get_settings
    
    logger.info("=" * 60)
    logger.info("BOT STARTING")
    logger.info("=" * 60)
    
    try:
        # Логируем ENV snapshot
        log_env_snapshot()
        
        # Загружаем настройки с валидацией
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
        logger.info(f"KIE mode: {'stub' if os.getenv('KIE_STUB') else ('real' if settings.kie_api_key else 'disabled')}")
        logger.info(f"Bot mode: {settings.bot_mode}")
        logger.info(f"Port: {settings.port if settings.port > 0 else 'disabled (Worker mode)'}")
        logger.info(f"Data directory: {settings.data_dir}")
        logger.info("=" * 60)
        
        # Проверяем data directory
        if not ensure_data_directory(settings.data_dir):
            logger.error("[FAIL] Data directory not writable, exiting")
            sys.exit(1)
        
        return settings
    except ValueError as e:
        logger.error("=" * 60)
        logger.error("CONFIGURATION VALIDATION FAILED")
        logger.error("=" * 60)
        logger.error(str(e))
        logger.error("=" * 60)
        sys.exit(1)
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


async def start_health_server(port: int) -> bool:
    """Запускает healthcheck сервер в том же event loop"""
    if port == 0:
        logger.info("[HEALTH] PORT not set, skipping healthcheck server (Worker mode)")
        return False
    
    try:
        from app.utils.healthcheck import start_health_server
        return await start_health_server(port=port)
    except Exception as e:
        logger.warning(f"[HEALTH] Failed to start health server: {e}")
        return False


async def run(settings, application):
    """Запускает бота (polling или webhook)"""
    global _application
    
    # Singleton lock должен быть получен ДО любых async операций
    from app.utils.singleton_lock import acquire_singleton_lock, release_singleton_lock
    
    if not acquire_singleton_lock():
        # acquire_singleton_lock уже вызвал exit(0) если lock не получен
        return
    
    try:
        # Запускаем healthcheck сервер (если PORT задан - Web Service режим)
        if settings.port > 0:
            logger.info(f"[HEALTH] Starting healthcheck server on port {settings.port} (Web Service mode)")
            await start_health_server(port=settings.port)
        else:
            logger.info("[HEALTH] Port not set, running in Worker mode (no healthcheck)")
        
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
            
            # Запускаем polling или webhook
            if settings.bot_mode == "webhook":
                if not settings.webhook_url:
                    logger.error("[FAIL] WEBHOOK_URL not set for webhook mode")
                    sys.exit(1)
                await application.bot.set_webhook(settings.webhook_url)
                logger.info(f"[RUN] Webhook set to {settings.webhook_url}")
                logger.info("[RUN] Webhook mode - bot is ready")
            else:
                # Polling mode
                logger.info("[RUN] Starting polling...")
                await application.bot.delete_webhook(drop_pending_updates=True)
                await application.updater.start_polling(drop_pending_updates=True)
                logger.info("[RUN] Polling started")
            
            # Ждем остановки
            try:
                await asyncio.Event().wait()  # Ждем бесконечно
            except KeyboardInterrupt:
                logger.info("[STOP] Bot stopped by user")
            finally:
                await application.stop()
                await application.shutdown()
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
        
        # Освобождаем singleton lock
        release_singleton_lock()


async def main():
    """Главная async функция"""
    try:
        # 1. Загружаем и валидируем настройки
        settings = load_and_validate_settings()
        
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

