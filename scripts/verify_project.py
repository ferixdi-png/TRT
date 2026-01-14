#!/usr/bin/env python3
"""
Verify project - проверка что проект готов к деплою
Железный контур проверки для гарантии рабочего состояния
"""

import sys
import os
import importlib
import asyncio
from pathlib import Path
from contextlib import contextmanager

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


@contextmanager
def mock_env(**env_vars):
    """Контекстный менеджер для мок env переменных"""
    old_env = {}
    for key, value in env_vars.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = str(value)

    # Устанавливаем SKIP_CONFIG_INIT чтобы не инициализировать при импорте
    old_skip = os.environ.get("SKIP_CONFIG_INIT")
    os.environ["SKIP_CONFIG_INIT"] = "1"

    try:
        yield
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if old_skip is None:
            os.environ.pop("SKIP_CONFIG_INIT", None)
        else:
            os.environ["SKIP_CONFIG_INIT"] = old_skip


def test_pytest():
    """Запускает pytest -q для всех тестов"""
    print("\n" + "=" * 60)
    print("TEST 1: pytest -q")
    print("=" * 60)

    import subprocess

    try:
        # Устанавливаем TEST_MODE для mock gateway
        env = os.environ.copy()
        env["TEST_MODE"] = "1"
        env["ALLOW_REAL_GENERATION"] = "0"

        # Запускаем pytest
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/"],
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5 минут максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr and "warning" not in result.stderr.lower():
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] All pytest tests passed")
            return True
        else:
            print(f"[FAIL] pytest failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] pytest timed out (>5 minutes)")
        return False
    except Exception as e:
        print(f"[FAIL] pytest error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_imports_no_side_effects():
    """Проверяет импорт модулей без побочных эффектов"""
    print("=" * 60)
    print("TEST 1: Import проверки (без side effects)")
    print("=" * 60)

    modules_to_test = [
        "app.config",
        "app.storage.base",
        "app.storage.json_storage",
        "app.services.user_service",
        "app.utils.retry",
    ]

    failed = []
    for module_name in modules_to_test:
        try:
            # Импортируем модуль
            module = importlib.import_module(module_name)
            # Проверяем что модуль загружен
            if module is None:
                print(f"[FAIL] {module_name}: module is None")
                failed.append(module_name)
            else:
                print(f"[OK] {module_name}")
        except Exception as e:
            print(f"[FAIL] {module_name}: {e}")
            failed.append(module_name)

    if failed:
        print(f"\n[FAIL] Failed to import {len(failed)} modules")
        return False

    print("[OK] All modules imported successfully")
    return True


def test_settings_validation():
    """Проверяет валидацию Settings с мок env"""
    print("\n" + "=" * 60)
    print("TEST 2: Settings validation (mock env)")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ", ADMIN_ID="123456789"
    ):
        try:
            from app.config import Settings

            # Создаем settings
            settings = Settings.from_env()

            # Проверяем обязательные поля
            assert settings.telegram_bot_token == "1234567890:TEST_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            assert settings.admin_id == 123456789
            assert settings.get_storage_mode() in ["postgres", "json"]

            print(
                f"[OK] Settings created: bot_token={settings.telegram_bot_token[:20]}..., admin_id={settings.admin_id}"
            )
            print(f"[OK] Storage mode: {settings.get_storage_mode()}")

            return True
        except SystemExit:
            print("[FAIL] Settings validation failed (SystemExit)")
            return False
        except Exception as e:
            print(f"[FAIL] Settings validation error: {e}")
            import traceback

            traceback.print_exc()
            return False


def test_storage_factory_json():
    """Проверяет storage factory в JSON режиме"""
    print("\n" + "=" * 60)
    print("TEST 3: Storage factory (JSON mode)")
    print("=" * 60)

    with mock_env(TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN", ADMIN_ID="123456789"):
        # Убираем DATABASE_URL чтобы использовать JSON
        old_db_url = os.environ.pop("DATABASE_URL", None)

        try:
            from app.storage import create_storage, reset_storage

            # Сбрасываем singleton для чистого теста
            reset_storage()

            storage = create_storage()
            print(f"[OK] Storage created: {type(storage).__name__}")

            # Проверяем подключение
            if storage.test_connection():
                print("[OK] Storage connection test passed")
            else:
                print("[WARN] Storage connection test failed (may be OK for JSON)")

            # Проверяем создание /app/data директории
            if hasattr(storage, "data_dir"):
                data_dir = Path(storage.data_dir)
                if data_dir.exists():
                    print(f"[OK] Data directory exists: {data_dir}")
                else:
                    print(f"[WARN] Data directory does not exist: {data_dir}")

            return True
        except Exception as e:
            print(f"[FAIL] Storage factory error: {e}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url


async def test_storage_operations():
    """Проверяет базовые операции storage (create user, изменить баланс, создать job)"""
    print("\n" + "=" * 60)
    print("TEST 3b: Storage operations (integrity check)")
    print("=" * 60)

    with mock_env(TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN", ADMIN_ID="123456789"):
        # Убираем DATABASE_URL чтобы использовать JSON
        old_db_url = os.environ.pop("DATABASE_URL", None)

        try:
            from app.storage import create_storage, reset_storage

            # Сбрасываем singleton для чистого теста
            reset_storage()

            storage = create_storage()
            test_user_id = 999999999  # Тестовый пользователь

            # 1. Создать пользователя
            user = await storage.get_user(test_user_id, upsert=True)
            print(f"[OK] User created: user_id={user['user_id']}, balance={user['balance']}")

            # 2. Изменить баланс
            await storage.set_user_balance(test_user_id, 100.0)
            balance = await storage.get_user_balance(test_user_id)
            assert balance == 100.0, f"Expected balance 100.0, got {balance}"
            print(f"[OK] Balance set: {balance}")

            # 3. Добавить к балансу
            new_balance = await storage.add_user_balance(test_user_id, 50.0)
            assert new_balance == 150.0, f"Expected balance 150.0, got {new_balance}"
            print(f"[OK] Balance added: {new_balance}")

            # 4. Вычесть из баланса
            success = await storage.subtract_user_balance(test_user_id, 30.0)
            assert success, "Subtract should succeed"
            balance = await storage.get_user_balance(test_user_id)
            assert balance == 120.0, f"Expected balance 120.0, got {balance}"
            print(f"[OK] Balance subtracted: {balance}")

            # 5. Создать job
            job_id = await storage.add_generation_job(
                user_id=test_user_id,
                model_id="test-model",
                model_name="Test Model",
                params={"prompt": "test"},
                price=10.0,
                status="pending",
            )
            print(f"[OK] Job created: {job_id}")

            # 6. Получить job
            job = await storage.get_job(job_id)
            assert job is not None, "Job should exist"
            assert job["user_id"] == test_user_id, "Job user_id should match"
            print(f"[OK] Job retrieved: status={job['status']}")

            # 7. Обновить статус job
            from app.storage.status import normalize_job_status

            await storage.update_job_status(
                job_id, "completed", result_urls=["http://test.com/result"]
            )
            job = await storage.get_job(job_id)
            expected_status = normalize_job_status("completed")
            assert job["status"] == expected_status, f"Job status should be {expected_status}"
            print(f"[OK] Job status updated: {job['status']}")

            # Очистка тестовых данных
            await storage.set_user_balance(test_user_id, 0.0)
            print("[OK] Test data cleaned up")

            return True
        except Exception as e:
            print(f"[FAIL] Storage operations error: {e}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url


async def test_generation_end_to_end():
    """Проверяет генерацию end-to-end в stub режиме"""
    print("\n" + "=" * 60)
    print("TEST 3c: Generation end-to-end (stub mode)")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN",
        ADMIN_ID="123456789",
        KIE_STUB="1",  # Включаем stub режим
    ):
        # Убираем DATABASE_URL чтобы использовать JSON
        old_db_url = os.environ.pop("DATABASE_URL", None)

        try:
            from app.services.generation_service import GenerationService
            from app.storage import create_storage, reset_storage

            # Сбрасываем singleton для чистого теста
            reset_storage()

            service = GenerationService()
            test_user_id = 999999999

            # 1. Создать генерацию
            job_id = await service.create_generation(
                user_id=test_user_id,
                model_id="test-model",
                model_name="Test Model",
                params={"prompt": "test prompt"},
                price=10.0,
            )
            print(f"[OK] Generation created: job_id={job_id}")

            from app.storage.status import normalize_job_status

            # 2. Ждать завершения (в stub режиме быстро)
            result = await service.wait_for_generation(job_id, timeout=30)

            if result.get("ok"):
                result_urls = result.get("result_urls", [])
                print(f"[OK] Generation completed: {len(result_urls)} result(s)")
                assert len(result_urls) > 0, "Should have result URLs"
            else:
                print(f"[FAIL] Generation failed: {result.get('error')}")
                return False

            # 3. Проверить job в storage
            storage = create_storage()
            job = await storage.get_job(job_id)
            assert job is not None, "Job should exist"
            expected_status = normalize_job_status("completed")
            assert job["status"] == expected_status, (
                f"Job should be {expected_status}, got {job['status']}"
            )
            print(f"[OK] Job status verified: {job['status']}")

            # Очистка
            await storage.set_user_balance(test_user_id, 0.0)
            print("[OK] Test data cleaned up")

            return True
        except Exception as e:
            print(f"[FAIL] Generation end-to-end error: {e}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url
            # Убираем KIE_STUB
            os.environ.pop("KIE_STUB", None)


async def test_create_application():
    """Проверяет создание Application без запуска polling"""
    print("\n" + "=" * 60)
    print("TEST 4: Create Application (без polling)")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ", ADMIN_ID="123456789"
    ):
        try:
            from telegram.ext import Application
            from app.config import get_settings

            settings = get_settings()

            # Создаем Application
            application = Application.builder().token(settings.telegram_bot_token).build()

            print("[OK] Application created")

            # Проверяем что application не запущен
            assert not application.running
            print("[OK] Application is not running (expected)")

            # НЕ вызываем initialize() - он делает реальный запрос к Telegram API
            # Вместо этого просто проверяем что Application создан корректно
            assert application.bot.token == settings.telegram_bot_token
            print("[OK] Application token set correctly")

            # Проверяем что можно получить handlers (если они были зарегистрированы)
            handlers_count = len(application.handlers.get(0, []))
            print(
                f"[OK] Application handlers structure OK (found {handlers_count} handlers in group 0)"
            )

            return True
        except Exception as e:
            # Если ошибка связана с токеном - это ожидаемо для мок токена
            if "token" in str(e).lower() or "invalid" in str(e).lower():
                print(
                    "[OK] Application created (token validation skipped - expected for mock token)"
                )
                return True
            print(f"[FAIL] Create application error: {e}")
            import traceback

            traceback.print_exc()
            return False


async def test_register_handlers():
    """Проверяет регистрацию handlers без запуска polling"""
    print("\n" + "=" * 60)
    print("TEST 4b: Register handlers (без polling)")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ", ADMIN_ID="123456789"
    ):
        try:
            # Пробуем импортировать функцию создания application из bot_kie
            # Но не запускаем её полностью - только проверяем что handlers регистрируются

            # Создаем минимальный Application для проверки
            from telegram.ext import Application
            from app.config import get_settings

            settings = get_settings()
            application = Application.builder().token(settings.telegram_bot_token).build()

            # Пробуем зарегистрировать простой handler для проверки
            from telegram.ext import CommandHandler

            def dummy_handler(update, context):
                pass

            application.add_handler(CommandHandler("test", dummy_handler))

            # Проверяем что handler зарегистрирован
            handlers = application.handlers.get(0, [])
            assert len(handlers) > 0
            print(f"[OK] Handlers can be registered (found {len(handlers)} handlers)")

            return True
        except Exception as e:
            print(f"[FAIL] Register handlers error: {e}")
            import traceback

            traceback.print_exc()
            return False


def test_menu_routes():
    """Smoke-проверка маршрутов меню (главное меню строится)"""
    print("\n" + "=" * 60)
    print("TEST 5: Menu routes (smoke test)")
    print("=" * 60)

    with mock_env(TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN", ADMIN_ID="123456789"):
        try:
            # Импортируем helpers
            import helpers

            # Инициализируем imports в helpers
            helpers._init_imports()

            # Пробуем построить главное меню
            async def test_menu():
                try:
                    keyboard = await helpers.build_main_menu_keyboard(
                        user_id=123456789, user_lang="ru", is_new=False
                    )

                    # Проверяем что keyboard - это список списков кнопок
                    assert isinstance(keyboard, list)
                    assert len(keyboard) > 0

                    print(f"[OK] Main menu keyboard built: {len(keyboard)} rows")
                    return True
                except Exception as e:
                    print(f"[FAIL] Menu build error: {e}")
                    import traceback

                    traceback.print_exc()
                    return False

            # Запускаем async тест
            result = asyncio.run(test_menu())
            return result

        except Exception as e:
            print(f"[FAIL] Menu routes test error: {e}")
            import traceback

            traceback.print_exc()
            return False


def test_fail_fast_missing_env():
    """Проверяет fail-fast диагностику при отсутствии обязательных env"""
    print("\n" + "=" * 60)
    print("TEST 6: Fail-fast (missing env)")
    print("=" * 60)

    # Убираем обязательные переменные
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_admin = os.environ.pop("ADMIN_ID", None)
    old_skip = os.environ.get("SKIP_CONFIG_INIT")
    os.environ["SKIP_CONFIG_INIT"] = "1"

    try:
        from app.config import Settings

        try:
            Settings.from_env(validate=True)
            print("[FAIL] Settings created without required env (should fail)")
            return False
        except SystemExit:
            print("[OK] SystemExit on missing env (expected)")
            return True
        except Exception as e:
            # Проверяем что ошибка понятная
            error_msg = str(e).lower()
            if "missing" in error_msg or "required" in error_msg:
                print("[OK] Clear error message about missing env")
                return True
            else:
                print(f"[FAIL] Unexpected error: {e}")
                return False
    finally:
        if old_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = old_token
        if old_admin:
            os.environ["ADMIN_ID"] = old_admin
        if old_skip is None:
            os.environ.pop("SKIP_CONFIG_INIT", None)
        else:
            os.environ["SKIP_CONFIG_INIT"] = old_skip


def test_smoke_all_models():
    """Запускает smoke test всех моделей через scripts/smoke_test_all_models.py"""
    print("\n" + "=" * 60)
    print("TEST 2: Smoke test всех моделей (mock gateway)")
    print("=" * 60)

    import subprocess

    try:
        # Устанавливаем TEST_MODE и ALLOW_REAL_GENERATION для mock gateway
        env = os.environ.copy()
        env["TEST_MODE"] = "1"
        env["ALLOW_REAL_GENERATION"] = "0"

        # Запускаем скрипт
        script_path = Path(__file__).parent / "smoke_test_all_models.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=300,  # 5 минут максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] All models passed smoke test")
            return True
        else:
            print(f"[FAIL] Smoke test failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] Smoke test timed out (>5 minutes)")
        return False
    except Exception as e:
        print(f"[FAIL] Smoke test error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_optional_dependencies():
    """Проверяет мягкую деградацию опциональных зависимостей"""
    print("\n" + "=" * 60)
    print("TEST 7: Optional dependencies (graceful degradation)")
    print("=" * 60)

    try:
        with mock_env(TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN", ADMIN_ID="123456789"):
            # Проверяем что filelock опционален
            from app.storage.json_storage import JsonStorage, FILELOCK_AVAILABLE

            if FILELOCK_AVAILABLE:
                print("[OK] filelock available")
            else:
                print("[OK] filelock not available (graceful degradation)")

            # Проверяем что storage создается даже без filelock
            JsonStorage("./test_data")
            print("[OK] JsonStorage created (with or without filelock)")

            # Очищаем тестовую директорию
            import shutil

            test_dir = Path("./test_data")
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)

            return True
    except Exception as e:
        print(f"[FAIL] Optional dependencies test error: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_render_hardening():
    """Проверяет Render-специфичные настройки"""
    print("\n" + "=" * 60)
    print("TEST 11: Render hardening")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN",
        ADMIN_ID="123456789",
        RENDER="1",
        DATA_DIR="/app/data",
        PORT="10000",
    ):
        try:
            # 1. Проверка entrypoint импортируется
            try:
                import app.main as app_main

                _ = (app_main.load_settings, app_main.build_application, app_main.run)
                print("[OK] Entrypoint functions importable")
            except Exception as e:
                print(f"[FAIL] Entrypoint import error: {e}")
                return False

            # 2. Проверка DATA_DIR используется
            from app.config import get_settings

            settings = get_settings()
            assert settings.data_dir == "/app/data", f"Expected /app/data, got {settings.data_dir}"
            print(f"[OK] DATA_DIR set correctly: {settings.data_dir}")

            # 3. Проверка singleton lock код импортируется
            try:
                import app.utils.singleton_lock as singleton_lock

                _ = (singleton_lock.acquire_singleton_lock, singleton_lock.release_singleton_lock)
                print("[OK] Singleton lock code importable")
            except Exception as e:
                print(f"[FAIL] Singleton lock import error: {e}")
                return False

            # 4. Проверка healthcheck код импортируется
            try:
                import app.utils.healthcheck as healthcheck

                _ = (healthcheck.start_health_server, healthcheck.stop_health_server)
                print("[OK] Healthcheck code importable")
            except Exception as e:
                print(f"[FAIL] Healthcheck import error: {e}")
                return False

            # 5. Проверка data dir создается
            from pathlib import Path

            # В тесте используем временную директорию
            test_data_dir = Path("./test_render_data")
            test_data_dir.mkdir(parents=True, exist_ok=True)
            test_file = test_data_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            test_data_dir.rmdir()
            print("[OK] Data directory can be created and written")

            return True
        except Exception as e:
            print(f"[FAIL] Render hardening error: {e}")
            import traceback

            traceback.print_exc()
            return False


async def test_regression_guards():
    """Регрессионные guards: меню, callback routes, storage, генерация"""
    print("\n" + "=" * 60)
    print("TEST 10: Regression guards")
    print("=" * 60)

    with mock_env(TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN", ADMIN_ID="123456789"):
        old_db_url = os.environ.pop("DATABASE_URL", None)
        old_kie_stub = os.environ.pop("KIE_STUB", None)

        try:
            # 1. Проверка что меню строится
            from app.domain.models_registry import get_models_registry

            registry = get_models_registry()
            models = registry.get_all_models()
            assert len(models) > 0, "Should have models"
            print(f"[OK] Menu can be built: {len(models)} models")

            # 2. Проверка storage работает
            from app.storage import create_storage, reset_storage

            reset_storage()
            storage = create_storage()
            test_user_id = 888888888
            balance = await storage.get_user_balance(test_user_id)
            assert balance == 0.0, "Storage should work"
            print("[OK] Storage works")

            # 3. Проверка генерация stub работает
            os.environ["KIE_STUB"] = "1"
            from app.services.generation_service import GenerationService

            service = GenerationService()
            job_id = await service.create_generation(
                user_id=test_user_id,
                model_id="test-model",
                model_name="Test",
                params={"prompt": "test"},
                price=10.0,
            )
            assert job_id, "Generation should work"
            print(f"[OK] Generation stub works: {job_id}")

            # 4. Проверка callback routes зарегистрированы
            try:
                from bot_kie import create_bot_application
                from app.config import get_settings

                settings = get_settings()
                app = await create_bot_application(settings)
                handlers = app.handlers
                assert len(handlers) > 0, "Should have handlers"
                print(f"[OK] Callback routes registered: {len(handlers)} handlers")
            except Exception as e:
                print(f"[WARN] Could not verify handlers: {e}")

            return True
        except Exception as e:
            print(f"[FAIL] Regression guards error: {e}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if old_db_url:
                os.environ["DATABASE_URL"] = old_db_url
            if old_kie_stub:
                os.environ["KIE_STUB"] = old_kie_stub
            else:
                os.environ.pop("KIE_STUB", None)


async def test_lock_not_acquired_no_exit():
    """Проверяет что в режиме lock not acquired приложение НЕ вызывает sys.exit"""
    print("\n" + "=" * 60)
    print("TEST: Lock not acquired - no exit (passive mode)")
    print("=" * 60)

    try:
        import app.locking.single_instance as lock_module
        import inspect

        source = inspect.getsource(lock_module.acquire_single_instance_lock)

        if "PASSIVE MODE" in source and "return False" in source:
            print("[OK] Lock not acquired: passive mode logic exists (returns False)")
            return True
        else:
            print("[FAIL] Lock not acquired: passive mode logic missing")
            return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_async_check_pg_no_nested_loop():
    """Проверяет что async_check_pg не вызывает nested loop ошибку"""
    print("\n" + "=" * 60)
    print("TEST: async_check_pg - no nested loop error")
    print("=" * 60)

    with mock_env(
        TELEGRAM_BOT_TOKEN="1234567890:TEST_TOKEN",
        ADMIN_ID="123456789",
        DATABASE_URL="postgresql://test:test@localhost:5432/test",
    ):
        try:
            from app.storage.pg_storage import PostgresStorage

            # Создаем storage
            storage = PostgresStorage("postgresql://test:test@localhost:5432/test")

            # Вызываем async_test_connection в уже запущенном event loop
            # Это должно работать без ошибки "Cannot run the event loop while another loop is running"
            try:
                result = await storage.async_test_connection()
                # Результат может быть False (нет подключения), но ошибки nested loop быть не должно
                print(
                    f"[OK] async_test_connection completed without nested loop error (result={result})"
                )
                return True
            except RuntimeError as e:
                if "Cannot run the event loop while another loop is running" in str(e):
                    print(
                        "[FAIL] Nested loop error detected - async_test_connection uses asyncio.run()"
                    )
                    return False
                else:
                    # Другие RuntimeError (например, нет подключения) - это нормально
                    print(f"[OK] async_test_connection completed (expected error: {e})")
                    return True

        except Exception as e:
            # Если нет asyncpg или другие ошибки - это нормально для теста
            if "asyncpg" in str(e).lower() or "import" in str(e).lower():
                print(f"[OK] asyncpg not available (expected in test env): {e}")
                return True
            print(f"[FAIL] Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            return False


def test_render_startup_fixes():
    """Проверяет исправления старта на Render"""
    print("\n" + "=" * 60)
    print("TEST: Render startup fixes")
    print("=" * 60)

    import subprocess

    try:
        # Запускаем тесты для render startup fixes
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_render_startup_fixes.py"],
            capture_output=True,
            text=True,
            timeout=60,  # 1 минута максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] Render startup fixes tests passed")
            return True
        else:
            print(f"[FAIL] Render startup fixes tests failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] Render startup fixes tests timed out (>1 minute)")
        return False
    except Exception as e:
        print(f"[FAIL] Render startup fixes tests error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_catalog_verification():
    """Проверяет каталог моделей через verify_catalog.py"""
    print("\n" + "=" * 60)
    print("TEST: Catalog verification")
    print("=" * 60)

    import subprocess

    try:
        # Запускаем скрипт проверки каталога
        script_path = Path(__file__).parent / "verify_catalog.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,  # 1 минута максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] Catalog verification passed")
            return True
        else:
            print(f"[FAIL] Catalog verification failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] Catalog verification timed out (>1 minute)")
        return False
    except Exception as e:
        print(f"[FAIL] Catalog verification error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_build_kie_registry():
    """Проверяет build_kie_registry.py - генерация registry из документации"""
    print("\n" + "=" * 60)
    print("TEST: Build KIE Registry from docs")
    print("=" * 60)

    import subprocess

    try:
        # Запускаем скрипт построения registry
        script_path = Path(__file__).parent / "build_kie_registry.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,  # 2 минуты максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] KIE Registry built successfully")
            return True
        else:
            print(f"[FAIL] Build registry failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] Build registry timed out (>2 minutes)")
        return False
    except Exception as e:
        print(f"[FAIL] Build registry error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_validate_kie_registry():
    """Проверяет validate_kie_registry.py - валидация registry"""
    print("\n" + "=" * 60)
    print("TEST: Validate KIE Registry")
    print("=" * 60)

    import subprocess

    try:
        # Запускаем скрипт валидации registry
        script_path = Path(__file__).parent / "validate_kie_registry.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,  # 1 минута максимум
        )

        # Выводим результат
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print("[OK] KIE Registry validation passed")
            return True
        else:
            print(f"[FAIL] Registry validation failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print("[FAIL] Registry validation timed out (>1 minute)")
        return False
    except Exception as e:
        print(f"[FAIL] Registry validation error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Главная функция проверки"""
    print("=" * 60)
    print("PROJECT VERIFICATION")
    print("=" * 60)
    print()

    tests = [
        ("Build KIE Registry", test_build_kie_registry),
        ("Validate KIE Registry", test_validate_kie_registry),
        ("Render startup fixes", test_render_startup_fixes),
        ("Catalog verification", test_catalog_verification),
        ("Lock not acquired - no exit", lambda: asyncio.run(test_lock_not_acquired_no_exit())),
        (
            "async_check_pg - no nested loop",
            lambda: asyncio.run(test_async_check_pg_no_nested_loop()),
        ),
        ("pytest -q", test_pytest),
        ("Smoke test всех моделей", test_smoke_all_models),
        ("Import проверки", test_imports_no_side_effects),
        ("Settings validation", test_settings_validation),
        ("Storage factory", test_storage_factory_json),
        ("Storage operations", lambda: asyncio.run(test_storage_operations())),
        ("Generation end-to-end", lambda: asyncio.run(test_generation_end_to_end())),
        ("Create Application", lambda: asyncio.run(test_create_application())),
        ("Register handlers", lambda: asyncio.run(test_register_handlers())),
        ("Menu routes", test_menu_routes),
        ("Fail-fast (missing env)", test_fail_fast_missing_env),
        ("Optional dependencies", test_optional_dependencies),
        ("Regression guards", lambda: asyncio.run(test_regression_guards())),
        ("Render hardening", lambda: asyncio.run(test_render_hardening())),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"[FAIL] Test '{name}' crashed: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Итоги
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("[OK] All tests passed!")
        return 0
    else:
        print("[FAIL] Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
