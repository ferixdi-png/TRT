"""
Тесты для исправлений старта на Render:
- async_check_pg не вызывает nested loop ошибку
- lock not acquired не вызывает sys.exit (passive mode)
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_async_check_pg_no_nested_loop():
    """
    Проверяет что async_check_pg не вызывает ошибку nested loop.
    """
    # Мокаем asyncpg
    with patch('app.storage.pg_storage.asyncpg') as mock_asyncpg:
        mock_pool = AsyncMock()
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        mock_pool.close = AsyncMock()
        
        from app.storage.pg_storage import PostgresStorage
        
        storage = PostgresStorage("postgresql://test:test@localhost/test")
        
        # Симулируем что мы в async контексте
        import asyncio
        
        async def test_async():
            # Вызываем async_test_connection в async контексте
            result = await storage.async_test_connection()
            assert isinstance(result, bool)
            # Не должно быть ошибки nested loop
        
        # Запускаем в event loop
        asyncio.run(test_async())


def test_lock_not_acquired_no_exit():
    """
    Проверяет что при lock not acquired процесс НЕ вызывает sys.exit (passive mode).
    """
    # Устанавливаем SINGLETON_LOCK_STRICT=0 (default на Render)
    with patch.dict(os.environ, {'SINGLETON_LOCK_STRICT': '0'}):
        with patch('app.locking.single_instance._acquire_postgres_lock', return_value=None):
            with patch('app.locking.single_instance._acquire_file_lock', return_value=None):
                with patch('sys.exit') as mock_exit:
                    from app.locking.single_instance import acquire_single_instance_lock
                    
                    # Вызываем функцию
                    result = acquire_single_instance_lock()
                    
                    # Проверяем что вернулось False (не exit)
                    assert result is False
                    
                    # Проверяем что sys.exit НЕ был вызван (в non-strict mode)
                    mock_exit.assert_not_called()


def test_lock_strict_mode_exits():
    """
    Проверяет что в STRICT mode при lock not acquired процесс вызывает exit.
    """
    # Устанавливаем SINGLETON_LOCK_STRICT=1
    with patch.dict(os.environ, {'SINGLETON_LOCK_STRICT': '1', 'DATABASE_URL': 'postgresql://test'}):
        with patch('app.locking.single_instance._acquire_postgres_lock', return_value=None):
            with patch('app.locking.single_instance._acquire_file_lock', return_value=None):
                with patch('sys.exit') as mock_exit:
                    from app.locking.single_instance import acquire_single_instance_lock
                    
                    # Вызываем функцию
                    try:
                        result = acquire_single_instance_lock()
                        # В strict mode должен быть exit (может быть вызван несколько раз из разных веток)
                        assert mock_exit.called, "sys.exit should be called in strict mode"
                        assert mock_exit.call_args_list[0][0][0] == 0, "exit code should be 0"
                    except SystemExit:
                        # Ожидаемо в strict mode
                        pass


def test_passive_mode_healthcheck_only():
    """
    Проверяет что в passive mode запускается только healthcheck.
    """
    with patch('app.locking.single_instance.acquire_single_instance_lock', return_value=False):
        with patch('app.main.start_health_server', new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            
            from app.config import Settings
            from app.main import run
            
            # Создаем mock settings
            settings = MagicMock(spec=Settings)
            settings.port = 10000
            settings.telegram_bot_token = "test_token"
            
            # Создаем mock application
            application = MagicMock()
            
            # Запускаем в async контексте
            import asyncio
            
            async def test_run():
                # Запускаем run с мокнутым lock (False)
                # Должен запуститься healthcheck и держать процесс живым
                # Но мы прервем через timeout
                try:
                    await asyncio.wait_for(
                        run(settings, application),
                        timeout=1.0  # Прерываем через 1 секунду
                    )
                except asyncio.TimeoutError:
                    pass  # Ожидаемо
            
            asyncio.run(test_run())
            
            # Проверяем что healthcheck был вызван
            mock_health.assert_called_once_with(port=10000)


def test_sync_test_connection_detects_running_loop():
    """
    Проверяет что sync test_connection обнаруживает запущенный loop и предупреждает.
    """
    from app.storage.pg_storage import PostgresStorage
    
    storage = PostgresStorage("postgresql://test:test@localhost/test")
    
    # Симулируем запущенный loop
    import asyncio
    
    async def test_with_loop():
        # Внутри async функции loop уже запущен
        # Вызываем sync test_connection - должно предупредить
        result = storage.test_connection()
        # Должно вернуть False и предупредить
        assert result is False
    
    # Запускаем в event loop
    asyncio.run(test_with_loop())


@pytest.fixture(autouse=True)
def reset_env():
    """Сбрасывает env переменные перед каждым тестом"""
    old_strict = os.environ.get('SINGLETON_LOCK_STRICT')
    old_db = os.environ.get('DATABASE_URL')
    
    yield
    
    if old_strict:
        os.environ['SINGLETON_LOCK_STRICT'] = old_strict
    elif 'SINGLETON_LOCK_STRICT' in os.environ:
        del os.environ['SINGLETON_LOCK_STRICT']
    
    if old_db:
        os.environ['DATABASE_URL'] = old_db
    elif 'DATABASE_URL' in os.environ:
        del os.environ['DATABASE_URL']

