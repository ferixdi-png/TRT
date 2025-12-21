#!/usr/bin/env python3
"""
Системный тест для проверки всех компонентов проекта.
Проверяет:
1. Advisory lock механизм
2. KIE client
3. Validator
4. Model registry
5. Universal handler
"""

import sys
import os
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

def test_imports():
    """Тест импортов всех модулей"""
    print("=" * 80)
    print("TEST 1: Импорты модулей")
    print("=" * 80)
    
    modules = [
        'kie_client',
        'kie_validator',
        'kie_universal_handler',
        'database',
        'render_singleton_lock'
    ]
    
    failed = []
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"[OK] {module_name}")
        except ImportError as e:
            print(f"[FAIL] {module_name}: {e}")
            failed.append(module_name)
    
    if failed:
        print(f"\n[FAIL] Не удалось импортировать: {', '.join(failed)}")
        return False
    else:
        print("\n[OK] Все модули импортированы успешно")
        return True


def test_model_registry():
    """Тест реестра моделей"""
    print("\n" + "=" * 80)
    print("TEST 2: Реестр моделей (models/kie_models.yaml)")
    print("=" * 80)
    
    try:
        from kie_validator import load_models_registry
        registry = load_models_registry()
        
        if not registry:
            print("[FAIL] Реестр пуст или не загружен")
            return False
        
        models = registry.get('models', {})
        if not models:
            print("[FAIL] Нет моделей в реестре")
            return False
        
        print(f"[OK] Загружено моделей: {len(models)}")
        
        # Проверяем model_type
        model_types = set()
        for model_id, model_info in models.items():
            model_type = model_info.get('model_type')
            if model_type:
                model_types.add(model_type)
        
        print(f"[OK] Найдено model_type: {len(model_types)}")
        for mt in sorted(model_types):
            count = sum(1 for m in models.values() if m.get('model_type') == mt)
            print(f"   - {mt}: {count} модель(ей)")
        
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка при загрузке реестра: {e}")
        return False


def test_validator():
    """Тест валидатора"""
    print("\n" + "=" * 80)
    print("TEST 3: Валидатор (kie_validator.py)")
    print("=" * 80)
    
    try:
        from kie_validator import validate, get_model_schema
        
        # Тест 1: Валидный input
        test_model = "z-image"
        schema = get_model_schema(test_model)
        if not schema:
            print(f"[FAIL] Модель {test_model} не найдена в реестре")
            return False
        
        valid_input = {
            "prompt": "test prompt",
            "aspect_ratio": "1:1"
        }
        
        is_valid, errors = validate(test_model, valid_input)
        if is_valid:
            print(f"[OK] Валидация валидного input для {test_model}: OK")
        else:
            print(f"[FAIL] Валидация валидного input для {test_model}: FAIL")
            print(f"   Ошибки: {errors}")
            return False
        
        # Тест 2: Невалидный input (отсутствует required)
        invalid_input = {
            "prompt": "test"
        }
        is_valid, errors = validate(test_model, invalid_input)
        if not is_valid:
            print(f"[OK] Валидация невалидного input для {test_model}: правильно отклонен")
        else:
            print(f"[FAIL] Валидация невалидного input для {test_model}: не отклонен")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании валидатора: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_kie_client():
    """Тест KIE client"""
    print("\n" + "=" * 80)
    print("TEST 4: KIE Client (kie_client.py)")
    print("=" * 80)
    
    try:
        from kie_client import get_client
        
        client = get_client()
        if not client:
            print("[FAIL] Не удалось создать KIE client")
            return False
        
        print(f"[OK] KIE client создан")
        print(f"   Base URL: {client.base_url}")
        print(f"   API Key: {'установлен' if client.api_key else 'НЕ установлен'}")
        
        # Проверяем методы
        methods = ['create_task', 'get_task_status', 'wait_task']
        for method in methods:
            if hasattr(client, method):
                print(f"[OK] Метод {method} существует")
            else:
                print(f"[FAIL] Метод {method} не найден")
                return False
        
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка при тестировании KIE client: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_universal_handler():
    """Тест универсального handler"""
    print("\n" + "=" * 80)
    print("TEST 5: Universal Handler (kie_universal_handler.py)")
    print("=" * 80)
    
    try:
        from kie_universal_handler import handle_kie_generation
        
        print("[OK] Функция handle_kie_generation импортирована")
        
        # Проверяем сигнатуру (не вызываем, так как нужен реальный API)
        import inspect
        sig = inspect.signature(handle_kie_generation)
        params = list(sig.parameters.keys())
        
        expected_params = ['model_id', 'user_input', 'callback_url']
        if all(p in params for p in expected_params):
            print(f"[OK] Сигнатура функции корректна: {params}")
        else:
            print(f"[FAIL] Неверная сигнатура: {params}, ожидается: {expected_params}")
            return False
        
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка при тестировании universal handler: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_advisory_lock():
    """Тест advisory lock механизма"""
    print("\n" + "=" * 80)
    print("TEST 6: Advisory Lock (render_singleton_lock.py)")
    print("=" * 80)
    
    try:
        from render_singleton_lock import make_lock_key
        
        # Тест генерации lock key
        test_token = "test_token_12345"
        lock_key = make_lock_key(test_token)
        
        if isinstance(lock_key, int) and -9223372036854775808 <= lock_key <= 9223372036854775807:
            print(f"[OK] Lock key сгенерирован: {lock_key}")
        else:
            print(f"[FAIL] Неверный формат lock key: {lock_key}")
            return False
        
        # Тест детерминированности
        lock_key2 = make_lock_key(test_token)
        if lock_key == lock_key2:
            print("[OK] Lock key детерминирован (одинаковый для одного токена)")
        else:
            print(f"[FAIL] Lock key не детерминирован: {lock_key} != {lock_key2}")
            return False
        
        return True
    except Exception as e:
        print(f"[FAIL] Ошибка при тестировании advisory lock: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Запуск всех тестов"""
    print("\n" + "=" * 80)
    print("СИСТЕМНЫЙ ТЕСТ ПРОЕКТА")
    print("=" * 80)
    
    tests = [
        ("Импорты", test_imports),
        ("Реестр моделей", test_model_registry),
        ("Валидатор", test_validator),
        ("KIE Client", test_kie_client),
        ("Universal Handler", test_universal_handler),
        ("Advisory Lock", test_advisory_lock),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n[FAIL] Критическая ошибка в тесте '{test_name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Итоги
    print("\n" + "=" * 80)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} - {test_name}")
    
    print(f"\nВсего: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n[OK] ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} тест(ов) не пройдено")
        return 1


if __name__ == "__main__":
    sys.exit(main())

