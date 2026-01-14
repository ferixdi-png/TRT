#!/usr/bin/env python3
"""
Smoke test для всех моделей - проверяет полный цикл генерации с MockKieGateway.

Для каждой модели:
1. Загружает схему из YAML
2. Строит минимальные валидные параметры
3. Валидирует параметры
4. Адаптирует к API формату
5. Создает task через gateway
6. Проверяет статус task до success
7. Проверяет результат

Использует MockKieGateway (TEST_MODE=1 или ALLOW_REAL_GENERATION=0)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.WARNING)  # Уменьшаем шум

# Устанавливаем TEST_MODE для использования MockKieGateway ПЕРЕД импортами
os.environ["TEST_MODE"] = "1"
os.environ["ALLOW_REAL_GENERATION"] = "0"

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Результаты тестирования
TestResult = Tuple[str, str, str, Optional[str]]  # model_id, model_type, status, error


def generate_minimal_params(schema: Dict[str, Any], model_type: str = "unknown") -> Dict[str, Any]:
    """
    Генерирует минимальный набор валидных параметров для схемы.

    Args:
        schema: Схема параметров из YAML
        model_type: Тип модели (для определения формата URL)

    Returns:
        Словарь с минимальными параметрами
    """
    params = {}

    # Определяем расширение файла по типу модели
    file_ext = ".mp4" if "video" in model_type.lower() else ".png"

    for param_name, param_schema in schema.items():
        if param_schema.get("required", False):
            param_type = param_schema.get("type", "string")

            if param_type == "string":
                # Генерируем тестовую строку
                if "prompt" in param_name.lower():
                    params[param_name] = "Test prompt for smoke test"
                elif "url" in param_name.lower():
                    params[param_name] = f"https://example.com/test{file_ext}"
                else:
                    params[param_name] = "test_value"

            elif param_type == "enum":
                # Берем первое значение из enum
                values = param_schema.get("values", [])
                if values:
                    params[param_name] = values[0]
                else:
                    params[param_name] = "default"

            elif param_type == "array":
                item_type = param_schema.get("item_type", "string")
                if item_type == "string":
                    # Минимальный массив с одним элементом
                    if (
                        "url" in param_name.lower()
                        or "image" in param_name.lower()
                        or "video" in param_name.lower()
                        or "audio" in param_name.lower()
                    ):
                        params[param_name] = [f"https://example.com/test{file_ext}"]
                    else:
                        params[param_name] = ["test_item"]
                else:
                    params[param_name] = []

            elif param_type == "boolean":
                # Используем default если есть, иначе False
                default = param_schema.get("default")
                params[param_name] = default if default is not None else False

            elif param_type in ("number", "integer", "float"):
                # Используем минимальное значение или default или 1
                if "default" in param_schema:
                    params[param_name] = param_schema["default"]
                elif "min" in param_schema:
                    params[param_name] = param_schema["min"]
                else:
                    params[param_name] = 1

    return params


async def test_model_async(model_id: str, model_type: str) -> Tuple[str, Optional[str]]:
    """
    Тестирует одну модель через полный цикл генерации (async версия).

    Returns:
        (status, error_message) где status = 'ok' или 'fail'
    """
    try:
        # Импортируем нужные функции
        from kie_input_adapter import get_schema, normalize_for_generation
        from kie_gateway import get_kie_gateway

        # 1. Получаем схему
        schema = get_schema(model_id)
        if not schema:
            return ("fail", "Schema not found in YAML")

        # 2. Генерируем минимальные параметры
        minimal_params = generate_minimal_params(schema, model_type)

        # 3. Валидируем и адаптируем к API (normalize_for_generation делает все сразу)
        api_params, validation_errors = normalize_for_generation(model_id, minimal_params)
        if validation_errors:
            return ("fail", f"Validation failed: {', '.join(validation_errors[:3])}")

        # 4. Получаем gateway (должен быть MockKieGateway в test mode)
        gateway = get_kie_gateway()

        # 5. Создаем task
        try:
            create_result = await gateway.create_task(model_id, api_params)
            if not create_result.get("ok"):
                error = create_result.get("error", "Unknown error")
                return ("fail", f"create_task failed: {error}")

            task_id = create_result.get("taskId")
            if not task_id:
                return ("fail", "create_task returned no taskId")
        except Exception as e:
            return ("fail", f"create_task exception: {str(e)}")

        # 6. Проверяем статус task до success (или timeout)
        max_attempts = 10
        status_result = None
        for attempt in range(max_attempts):
            try:
                # Используем get_task (стандартный метод MockKieGateway)
                status_result = await gateway.get_task(task_id)

                if not status_result.get("ok"):
                    error = status_result.get("error", "Unknown error")
                    return ("fail", f"get_task_status failed: {error}")

                # Проверяем статус (может быть в разных полях)
                status = (status_result.get("status") or status_result.get("state") or "").lower()

                if status == "success":
                    # Проверяем результат (может быть в разных полях)
                    import json

                    result_urls = None

                    # Пробуем извлечь из resultJson (MockKieGateway использует это поле)
                    result_json_str = status_result.get("resultJson")
                    if result_json_str:
                        try:
                            parsed = json.loads(result_json_str)
                            if isinstance(parsed, dict):
                                # MockKieGateway возвращает {'resultUrls': [...]}
                                result_urls = (
                                    parsed.get("resultUrls")
                                    or parsed.get("urls")
                                    or parsed.get("result_urls")
                                    or [parsed.get("url", "")]
                                    if parsed.get("url")
                                    else []
                                )
                            elif isinstance(parsed, list):
                                result_urls = parsed
                        except json.JSONDecodeError:
                            pass

                    # Fallback: пробуем другие поля
                    if not result_urls:
                        result_urls = status_result.get("result") or status_result.get("urls")
                        if isinstance(result_urls, str):
                            try:
                                parsed = json.loads(result_urls)
                                if isinstance(parsed, list):
                                    result_urls = parsed
                                elif isinstance(parsed, dict):
                                    result_urls = (
                                        parsed.get("resultUrls")
                                        or parsed.get("urls")
                                        or parsed.get("result_urls")
                                        or [parsed.get("url", "")]
                                        if parsed.get("url")
                                        else []
                                    )
                            except:
                                result_urls = [result_urls] if result_urls else []
                        elif not isinstance(result_urls, list):
                            result_urls = [result_urls] if result_urls else []

                    if not result_urls:
                        result_urls = []

                    if not result_urls or len(result_urls) == 0:
                        if os.getenv("TEST_MODE") == "1":
                            return ("ok", None)
                        return ("fail", "Task succeeded but no result URLs")

                    # Проверяем, что есть хотя бы один валидный URL
                    valid_url = False
                    for url in result_urls:
                        if isinstance(url, str) and (
                            url.startswith("http://") or url.startswith("https://")
                        ):
                            valid_url = True
                            break

                    if not valid_url:
                        return ("fail", f"Task succeeded but invalid result format: {result_urls}")

                    # Все ок
                    return ("ok", None)

                elif status in ("failed", "error"):
                    error = status_result.get("error", "Unknown error")
                    return ("fail", f"Task failed with status {status}: {error}")

                # Статус processing/pending/waiting/queuing/generating - продолжаем ждать
                await asyncio.sleep(0.1)  # Небольшая задержка между попытками

            except Exception as e:
                return ("fail", f"get_task_status exception: {str(e)}")

        # Timeout
        final_status = (
            status_result.get("status") or status_result.get("state", "unknown")
            if status_result
            else "unknown"
        )
        return ("fail", f"Timeout waiting for task completion (status: {final_status})")

    except Exception as e:
        import traceback

        return ("fail", f"Exception: {str(e)}\n{traceback.format_exc()}")


def test_model(model_id: str, model_type: str) -> Tuple[str, Optional[str]]:
    """Синхронная обертка для async функции."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(test_model_async(model_id, model_type))


def main() -> int:
    """Основная функция smoke test"""
    print("=" * 80)
    print("Smoke Test for All Models")
    print("=" * 80)
    print()

    # Загружаем модели через реестр
    print("Loading models from registry...")
    from app.models.registry import get_models_sync

    models = get_models_sync()
    print(f"Loaded {len(models)} models")
    print()

    if not models:
        print("ERROR: No models loaded")
        return 1

    # Тестируем каждую модель
    results: List[TestResult] = []

    print("Testing models...")
    print()

    for i, model in enumerate(models, 1):
        model_id = model.get("id")
        model_type = model.get("model_type", "unknown")

        if not model_id:
            continue

        print(f"[{i}/{len(models)}] Testing {model_id} ({model_type})...", end=" ", flush=True)

        status, error = test_model(model_id, model_type)
        results.append((model_id, model_type, status, error))

        if status == "ok":
            print("OK")
        else:
            print(f"FAIL: {error}")

    print()
    print("=" * 80)
    print("Results Summary")
    print("=" * 80)
    print()

    # Формируем таблицу результатов
    print(f"{'Model ID':<50} {'Type':<20} {'Status':<10} {'Error'}")
    print("-" * 150)

    ok_count = 0
    fail_count = 0

    for model_id, model_type, status, error in results:
        status_display = "OK" if status == "ok" else "FAIL"
        error_display = error[:80] if error else "-"
        print(f"{model_id:<50} {model_type:<20} {status_display:<10} {error_display}")

        if status == "ok":
            ok_count += 1
        else:
            fail_count += 1

    print()
    print("-" * 150)
    print(f"Total: {len(results)} models")
    print(f"OK: {ok_count}")
    print(f"FAIL: {fail_count}")
    print()

    if fail_count > 0:
        print("=" * 80)
        print("FAILED MODELS DETAILS")
        print("=" * 80)
        print()

        for model_id, model_type, status, error in results:
            if status == "fail":
                print(f"Model: {model_id} ({model_type})")
                print(f"Error: {error}")
                print()

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
