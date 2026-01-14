"""
Тест дешевых моделей KIE AI
Проверяем работоспособность бесплатных и дешевых моделей
"""
import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.kie.generator import KieGenerator
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


async def test_model(model_id: str, test_inputs: dict, description: str = ""):
    """
    Тестирует одну модель
    
    Args:
        model_id: ID модели для теста
        test_inputs: Входные данные для генерации
        description: Описание теста
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"🧪 ТЕСТ: {model_id}")
    if description:
        logger.info(f"📝 {description}")
    logger.info(f"{'='*80}")
    
    try:
        generator = KieGenerator()
        
        # Пробуем сгенерировать
        logger.info(f"🚀 Запуск генерации...")
        logger.info(f"📥 Входные данные: {test_inputs}")
        
        result = await generator.generate(
            model_id=model_id,
            user_inputs=test_inputs,
            timeout=120,  # 2 минуты максимум
            poll_interval=2.0
        )
        
        # Проверяем результат
        success = result.get('success', False)
        
        if success:
            logger.info(f"✅ УСПЕХ | Model: {model_id}")
            logger.info(f"📊 Результат: {result.get('message', 'OK')}")
            
            # Показываем URLs если есть
            urls = result.get('result_urls', [])
            if urls:
                logger.info(f"🖼️  Результаты ({len(urls)} файлов):")
                for i, url in enumerate(urls[:3], 1):  # Первые 3
                    logger.info(f"   {i}. {url[:80]}...")
            
            # Показываем task_id
            task_id = result.get('task_id')
            if task_id:
                logger.info(f"🆔 Task ID: {task_id}")
                
            return {"status": "PASS", "model": model_id, "result": result}
        else:
            logger.error(f"❌ ОШИБКА | Model: {model_id}")
            logger.error(f"💥 Сообщение: {result.get('message', 'Unknown error')}")
            logger.error(f"🔧 Error code: {result.get('error_code', 'N/A')}")
            
            return {"status": "FAIL", "model": model_id, "error": result.get('message')}
            
    except Exception as e:
        logger.error(f"💀 EXCEPTION | Model: {model_id} | {type(e).__name__}: {str(e)}", exc_info=True)
        return {"status": "ERROR", "model": model_id, "exception": str(e)}


async def main():
    """Основная функция тестирования"""
    
    logger.info("\n" + "="*80)
    logger.info("🎯 ТЕСТИРОВАНИЕ ДЕШЕВЫХ МОДЕЛЕЙ KIE AI")
    logger.info(f"⏰ Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80 + "\n")
    
    # Проверяем наличие API ключа
    api_key = os.getenv('KIE_API_KEY')
    if not api_key:
        logger.error("❌ KIE_API_KEY не найден в переменных окружения!")
        logger.error("Установите: export KIE_API_KEY='your-key-here'")
        return
    
    logger.info(f"🔑 API Key: {api_key[:10]}...{api_key[-10:]}")
    
    # Список моделей для тестирования (ВСЕ БЕСПЛАТНЫЕ!)
    test_cases = [
        {
            "model_id": "z-image",
            "inputs": {
                "prompt": "A cute cat in space, realistic style, 4K quality",
                "aspect_ratio": "1:1"
            },
            "description": "🆓 z-image (0₽) - фотореалистичные изображения"
        },
        {
            "model_id": "qwen/text-to-image",
            "inputs": {
                "prompt": "A futuristic city at sunset, cyberpunk style, neon lights",
                "guidance_scale": 7.5,
                "num_inference_steps": 30
            },
            "description": "🆓 Qwen Text-to-Image (0₽) - от Alibaba"
        },
        {
            "model_id": "text-to-image",
            "inputs": {
                "prompt": "A beautiful landscape with mountains and lake, high quality"
            },
            "description": "🆓 Text-to-Image (0₽) - базовая бесплатная модель"
        },
        {
            "model_id": "image-to-image",
            "inputs": {
                "prompt": "Transform into anime style",
                "image_url": "https://picsum.photos/512/512"
            },
            "description": "🆓 Image-to-Image (0₽) - трансформация изображений"
        }
    ]
    
    results = []
    
    # Запускаем тесты последовательно
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\n{'─'*80}")
        logger.info(f"📌 ТЕСТ {i}/{len(test_cases)}")
        logger.info(f"{'─'*80}")
        
        result = await test_model(
            model_id=test_case["model_id"],
            test_inputs=test_case["inputs"],
            description=test_case.get("description", "")
        )
        
        results.append(result)
        
        # Пауза между тестами
        if i < len(test_cases):
            logger.info("\n⏸️  Пауза 3 секунды перед следующим тестом...")
            await asyncio.sleep(3)
    
    # Итоговый отчет
    logger.info("\n" + "="*80)
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ")
    logger.info("="*80)
    
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    
    logger.info(f"✅ Успешно: {passed}/{len(results)}")
    logger.info(f"❌ Ошибок: {failed}/{len(results)}")
    logger.info(f"💀 Исключений: {errors}/{len(results)}")
    
    logger.info("\nДетали:")
    for i, result in enumerate(results, 1):
        status_emoji = {
            'PASS': '✅',
            'FAIL': '❌',
            'ERROR': '💀'
        }.get(result['status'], '❓')
        
        logger.info(f"  {i}. {status_emoji} {result['model']}: {result['status']}")
    
    logger.info("\n" + "="*80)
    logger.info(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80 + "\n")
    
    # Возвращаем код выхода
    return 0 if failed == 0 and errors == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
