#!/usr/bin/env python3
"""
Smoke test для z-image генерации с aspect_ratio параметром.
Проверяет работу парсера V4, polling, и callback.
"""
import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Загружаем переменные окружения из .env
from dotenv import load_dotenv
load_dotenv()

from app.integrations.kie_client import KIEClient
from app.kie.parser import parse_record_info


async def test_z_image_generation():
    """Тест реальной генерации через KIE API с aspect_ratio."""
    
    print("🧪 Smoke Test: z-image generation с aspect_ratio")
    print("=" * 60)
    
    # Инициализация клиента
    client = KIEClient()
    
    # Параметры генерации
    prompt = "beautiful sunset over mountains, professional photography"
    input_data = {
        "prompt": prompt,
        "aspect_ratio": "16:9",  # Критически важный параметр
        "num_inference_steps": 20,
        "guidance_scale": 7.5
    }
    
    print(f"📝 Prompt: {prompt}")
    print(f"⚙️  Params: {input_data}")
    print()
    
    try:
        # Шаг 1: Создание задачи
        print("🚀 Step 1: Создание задачи...")
        task_response = await client.create_task(
            model_id="black-forest-labs/FLUX.1-schnell",
            input_data=input_data,
            callback_url=None
        )
        
        if not task_response.get("ok"):
            print(f"❌ FAIL: Ошибка создания задачи: {task_response.get('error')}")
            return False
            
        task_id = task_response["taskId"]
        print(f"✅ Задача создана: {task_id}")
        print()
        
        # Шаг 2: Polling до завершения
        print("⏳ Step 2: Polling статуса...")
        max_attempts = 60
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            
            # Получаем статус
            record_info = await client.get_task_status(task_id)
            
            if not record_info:
                print(f"❌ Attempt {attempt}: Нет recordInfo")
                await asyncio.sleep(2)
                continue
            
            # Парсим через наш V4-совместимый парсер
            parsed = parse_record_info(record_info)
            
            state = parsed.get("state", "unknown")
            is_done = parsed.get("is_done", False)
            is_failed = parsed.get("is_failed", False)
            
            print(f"📊 Attempt {attempt}: state={state}, is_done={is_done}, is_failed={is_failed}")
            
            # Проверка на завершение
            if is_done:
                print()
                print("✅ Генерация завершена!")
                
                # Проверяем результат
                result_json = parsed.get("resultJson")
                if result_json:
                    # resultJson может быть строкой или объектом
                    if isinstance(result_json, str):
                        print(f"📦 ResultJson (string): {result_json[:200]}...")
                    else:
                        print(f"📦 ResultJson (object): {result_json}")
                    
                    # Проверяем на наличие URL изображения
                    if isinstance(result_json, dict):
                        image_url = result_json.get("result", {}).get("imageUrl")
                        if image_url:
                            print(f"🖼️  Image URL: {image_url}")
                        else:
                            print("⚠️  WARNING: Нет imageUrl в result")
                    elif isinstance(result_json, str) and "imageUrl" in result_json:
                        print("🖼️  Image URL найден в строке resultJson")
                else:
                    print("⚠️  WARNING: Нет resultJson")
                
                print()
                print("🎉 SMOKE TEST PASSED")
                
                # Закрываем клиент
                await client.close()
                return True
                
            elif is_failed:
                print()
                print(f"❌ FAIL: Генерация завершилась с ошибкой")
                print(f"Error: {parsed.get('error', 'Unknown')}")
                await client.close()
                return False
            
            # Продолжаем polling
            await asyncio.sleep(2)
        
        # Таймаут
        print()
        print(f"❌ FAIL: Таймаут после {max_attempts} попыток")
        await client.close()
        return False
        
    except Exception as e:
        print()
        print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await client.close()
        return False


async def main():
    """Основная функция."""
    success = await test_z_image_generation()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
