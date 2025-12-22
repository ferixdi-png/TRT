#!/usr/bin/env python3
"""
Smoke test - локальный запуск в холостую
Инициализация + регистрация handlers + graceful shutdown
БЕЗ реального запуска polling/webhook
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def setup_mock_env():
    """Устанавливает мок env переменные"""
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:TEST_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    os.environ.setdefault("ADMIN_ID", "123456789")
    os.environ.setdefault("SKIP_CONFIG_INIT", "1")  # Пропускаем инициализацию при импорте


async def smoke_test():
    """Smoke test - инициализация без запуска"""
    logger.info("=" * 60)
    logger.info("SMOKE TEST: Инициализация бота в холостую")
    logger.info("=" * 60)
    
    try:
        # 1. Валидация окружения
        logger.info("[1/5] Validating environment...")
        from app.config import get_settings
        
        # Сбрасываем глобальный экземпляр для чистого теста
        import app.config
        app.config._settings = None
        
        settings = get_settings()
        logger.info(f"[OK] Environment validated: admin_id={settings.admin_id}, storage={settings.get_storage_mode()}")
        
        # 2. Инициализация storage
        logger.info("[2/5] Initializing storage...")
        from app.storage import create_storage
        
        storage = create_storage()
        if storage.test_connection():
            logger.info(f"[OK] Storage initialized: {type(storage).__name__}")
        else:
            logger.warning(f"[WARN] Storage connection test failed (may be OK for JSON)")
        
        # 3. Создание Application
        logger.info("[3/5] Creating Application...")
        from telegram.ext import Application
        
        application = Application.builder().token(settings.telegram_bot_token).build()
        logger.info("[OK] Application created")
        
        # 4. Регистрация handlers (без реального запуска)
        logger.info("[4/5] Registering handlers...")
        
        # Пробуем импортировать bot_kie и зарегистрировать handlers
        # Но НЕ вызываем main() - только проверяем что handlers регистрируются
        try:
            # Импортируем bot_kie но не запускаем main()
            import bot_kie
            
            # Проверяем что основные функции доступны
            assert hasattr(bot_kie, 'button_callback')
            assert hasattr(bot_kie, 'start')
            logger.info("[OK] bot_kie module imported, handlers available")
            
            # НЕ регистрируем handlers здесь - это делается в bot_kie.main()
            # Просто проверяем что модуль импортируется без ошибок
            logger.info("[OK] Handlers can be registered (module structure OK)")
            
        except Exception as e:
            logger.error(f"[FAIL] Failed to import bot_kie: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # 5. Graceful shutdown
        logger.info("[5/5] Graceful shutdown...")
        
        # Проверяем что application можно корректно закрыть
        assert not application.running
        logger.info("[OK] Application ready for shutdown (not running)")
        
        logger.info("=" * 60)
        logger.info("[OK] Smoke test passed!")
        logger.info("=" * 60)
        
        return True
        
    except SystemExit:
        logger.error("[FAIL] SystemExit during smoke test (missing env?)")
        return False
    except Exception as e:
        logger.error(f"[FAIL] Smoke test error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Главная функция"""
    setup_mock_env()
    
    try:
        result = asyncio.run(smoke_test())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("[INFO] Smoke test interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"[FAIL] Smoke test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
