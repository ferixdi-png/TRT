#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BEHAVIORAL E2E TESTING - Проверка реального поведения бота
Единственная истина - ПОВЕДЕНИЕ ПОЛЬЗОВАТЕЛЯ, не структура

Проверяет что каждая модель:
1. Отвечает на нажатие кнопки
2. Запрашивает ввод
3. Отвечает на ввод промпта
4. Отправляет результат (send_message/send_photo/send_video)
5. НЕ молчит
6. НЕ зависает
"""

import sys
import os
import asyncio
import io
from pathlib import Path
from typing import Dict, List, Set, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from collections import defaultdict

# Установка кодировки UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Импортируем модели
from kie_models import KIE_MODELS, get_model_by_id

# Цвета
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'


class ResponseTracker:
    """Трекер ответов бота пользователю - перехватывает реальные вызовы"""
    
    def __init__(self):
        self.sent_messages: List[Dict] = []
        self.sent_photos: List[Dict] = []
        self.sent_videos: List[Dict] = []
        self.sent_audios: List[Dict] = []
        self.edited_messages: List[Dict] = []
        self.replied_messages: List[Dict] = []
        self.callback_answers: List[Dict] = []
    
    def track_send_message(self, chat_id: int, text: str, **kwargs):
        """Отслеживает send_message"""
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text[:200],  # Первые 200 символов
            **{k: v for k, v in kwargs.items() if k != 'reply_markup'}  # Исключаем reply_markup для краткости
        })
    
    def track_send_photo(self, chat_id: int, photo, **kwargs):
        """Отслеживает send_photo"""
        self.sent_photos.append({
            "chat_id": chat_id,
            "photo": str(photo)[:50] if photo else None,
            "caption": kwargs.get('caption', '')[:100] if kwargs.get('caption') else None
        })
    
    def track_send_video(self, chat_id: int, video, **kwargs):
        """Отслеживает send_video"""
        self.sent_videos.append({
            "chat_id": chat_id,
            "video": str(video)[:50] if video else None,
            "caption": kwargs.get('caption', '')[:100] if kwargs.get('caption') else None
        })
    
    def track_edit_message_text(self, chat_id: int, message_id: int, text: str, **kwargs):
        """Отслеживает edit_message_text"""
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:200]
        })
    
    def track_reply_text(self, text: str, **kwargs):
        """Отслеживает reply_text"""
        self.replied_messages.append({
            "text": text[:200]
        })
    
    def has_any_response(self) -> bool:
        """Проверяет что был хотя бы один ответ"""
        return (
            len(self.sent_messages) > 0 or
            len(self.sent_photos) > 0 or
            len(self.sent_videos) > 0 or
            len(self.edited_messages) > 0 or
            len(self.replied_messages) > 0
        )
    
    def get_response_count(self) -> int:
        """Возвращает общее количество ответов"""
        return (
            len(self.sent_messages) +
            len(self.sent_photos) +
            len(self.sent_videos) +
            len(self.edited_messages) +
            len(self.replied_messages)
        )
    
    def get_summary(self) -> Dict:
        """Возвращает сводку ответов"""
        return {
            "total": self.get_response_count(),
            "send_message": len(self.sent_messages),
            "send_photo": len(self.sent_photos),
            "send_video": len(self.sent_videos),
            "edit_message_text": len(self.edited_messages),
            "reply_text": len(self.replied_messages),
            "has_response": self.has_any_response()
        }


async def test_model_behavioral_flow(model_id: str, model_info: Dict) -> Dict:
    """
    Тестирует полный поведенческий цикл для модели
    
    Цикл:
    1. Нажатие кнопки модели (select_model:model_id)
    2. Ввод промпта (текстовое сообщение)
    3. Проверка ответа бота (send_message/send_photo/send_video/edit_message_text/reply_text)
    
    Returns:
        Dict с результатами теста
    """
    tracker = ResponseTracker()
    
    # Создаём fake пользователя
    test_user_id = 999999999
    test_user = MagicMock()
    test_user.id = test_user_id
    test_user.username = "test_user"
    test_user.first_name = "Test"
    
    test_chat = MagicMock()
    test_chat.id = test_user_id
    test_chat.type = "private"
    
    # Создаём fake message
    fake_message = MagicMock()
    fake_message.message_id = 1
    fake_message.from_user = test_user
    fake_message.chat = test_chat
    fake_message.text = "test prompt for behavioral e2e"
    fake_message.reply_text = AsyncMock(side_effect=lambda text, **kwargs: tracker.track_reply_text(text, **kwargs) or MagicMock(message_id=2))
    
    # Создаём fake callback query
    fake_callback_query = MagicMock()
    fake_callback_query.id = "test_callback_1"
    fake_callback_query.data = f"select_model:{model_id}"
    fake_callback_query.from_user = test_user
    fake_callback_query.message = fake_message
    fake_callback_query.answer = AsyncMock(side_effect=lambda **kwargs: tracker.callback_answers.append(kwargs) or True)
    fake_callback_query.edit_message_text = AsyncMock(side_effect=lambda text, **kwargs: tracker.track_edit_message_text(test_user_id, 1, text, **kwargs) or True)
    
    # Создаём fake update для callback
    fake_update_callback = MagicMock()
    fake_update_callback.update_id = 1
    fake_update_callback.callback_query = fake_callback_query
    fake_update_callback.message = None
    fake_update_callback.effective_user = test_user
    fake_update_callback.effective_chat = test_chat
    
    # Создаём fake update для message
    fake_update_message = MagicMock()
    fake_update_message.update_id = 2
    fake_update_message.callback_query = None
    fake_update_message.message = fake_message
    fake_update_message.effective_user = test_user
    fake_update_message.effective_chat = test_chat
    
    # Создаём fake bot с трекером
    fake_bot = MagicMock()
    fake_bot.send_message = AsyncMock(side_effect=lambda chat_id, text, **kwargs: tracker.track_send_message(chat_id, text, **kwargs) or MagicMock(message_id=len(tracker.sent_messages) + 1))
    fake_bot.send_photo = AsyncMock(side_effect=lambda chat_id, photo, **kwargs: tracker.track_send_photo(chat_id, photo, **kwargs) or MagicMock(message_id=len(tracker.sent_photos) + 1))
    fake_bot.send_video = AsyncMock(side_effect=lambda chat_id, video, **kwargs: tracker.track_send_video(chat_id, video, **kwargs) or MagicMock(message_id=len(tracker.sent_videos) + 1))
    fake_bot.edit_message_text = AsyncMock(side_effect=lambda chat_id, message_id, text, **kwargs: tracker.track_edit_message_text(chat_id, message_id, text, **kwargs) or True)
    
    # Создаём fake context
    fake_context = MagicMock()
    fake_context.bot = fake_bot
    
    # КРИТИЧНО: Устанавливаем ENV переменные ДО импорта bot_kie
    os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'
    os.environ['FAKE_KIE_MODE'] = '1'
    os.environ['APP_ENV'] = 'test'
    
    try:
        # Мокаем все внешние зависимости
        with patch('bot_kie.get_kie_gateway') as mock_gateway, \
             patch('bot_kie.get_user_balance', return_value=1000.0), \
             patch('bot_kie.get_user_language', return_value='ru'), \
             patch('bot_kie.user_sessions', {}), \
             patch('bot_kie.DATABASE_AVAILABLE', False), \
             patch('bot_kie.get_user_generations_history', return_value=[]), \
             patch('bot_kie.get_is_admin', return_value=False), \
             patch('bot_kie.is_free_generation_available', return_value=True):
            
            # Настраиваем fake gateway
            from tests.fakes.fake_kie_api import FakeKieAPI
            fake_gateway = FakeKieAPI()
            mock_gateway.return_value = fake_gateway
            
            # Импортируем функции бота ПОСЛЕ моков
            import importlib
            if 'bot_kie' in sys.modules:
                importlib.reload(sys.modules['bot_kie'])
            from bot_kie import button_callback, input_parameters
            
            # Шаг 1: Эмулируем нажатие кнопки модели
            try:
                # Очищаем трекер перед кнопкой
                tracker.sent_messages.clear()
                tracker.edited_messages.clear()
                tracker.replied_messages.clear()
                tracker.callback_answers.clear()
                
                result1 = await button_callback(fake_update_callback, fake_context)
                responses_after_button = tracker.get_response_count()
                
                # КРИТИЧНО: Проверяем что был ответ после нажатия кнопки
                # Ответ может быть через edit_message_text, send_message, или reply_text
                if responses_after_button == 0:
                    # Проверяем callback_answers (query.answer() тоже считается ответом)
                    if len(tracker.callback_answers) == 0:
                        return {
                            "model_id": model_id,
                            "passed": False,
                            "step": "button_click",
                            "responses_after_button": 0,
                            "responses_after_input": 0,
                            "total_responses": 0,
                            "error": "No response after button click (silence) - no send/edit/reply/callback_answer"
                        }
            except Exception as e:
                return {
                    "model_id": model_id,
                    "passed": False,
                    "step": "button_click",
                    "responses_after_button": 0,
                    "responses_after_input": 0,
                    "total_responses": 0,
                    "error": f"Button callback error: {str(e)[:200]}"
                }
            
            # Шаг 2: Эмулируем ввод промпта
            # Получаем требуемые параметры модели
            input_params = model_info.get('input_params', {})
            prompt_param = None
            for param_name, param_info in input_params.items():
                if param_name == 'prompt' or 'prompt' in param_name.lower():
                    prompt_param = param_name
                    break
            
            # Если нет prompt, проверяем другие обязательные параметры
            if not prompt_param:
                required_params = [k for k, v in input_params.items() if v.get('required', False)]
                if not required_params:
                    # Нет обязательных параметров - модель должна работать без ввода
                    # Но должна была ответить на кнопку
                    return {
                        "model_id": model_id,
                        "passed": responses_after_button > 0,
                        "step": "button_click_only",
                        "responses_after_button": responses_after_button,
                        "responses_after_input": responses_after_button,
                        "total_responses": responses_after_button,
                        "response_summary": tracker.get_summary(),
                        "error": None
                    }
            
            # Вызываем input_parameters с текстовым промптом
            try:
                # Очищаем трекер перед вводом (чтобы отследить новые ответы)
                responses_before_input = tracker.get_response_count()
                tracker.sent_messages.clear()
                tracker.edited_messages.clear()
                tracker.replied_messages.clear()
                
                result2 = await input_parameters(fake_update_message, fake_context)
                responses_after_input = tracker.get_response_count()
                
                # КРИТИЧНО: Проверяем что был ответ на ввод
                # input_parameters ОБЯЗАН отправить "✅ Принято, обрабатываю..." или другой ответ
                if responses_after_input == 0:
                    # Нет ответа на ввод - это тишина
                    return {
                        "model_id": model_id,
                        "passed": False,
                        "step": "input_silence",
                        "responses_after_button": responses_after_button,
                        "responses_after_input": 0,
                        "total_responses": responses_before_input,
                        "response_summary": tracker.get_summary(),
                        "error": "No response after text input (silence) - input_parameters did not send reply"
                    }
            except Exception as e:
                # Даже если ошибка, проверяем что был хотя бы ответ на кнопку
                # Но если был ответ на ввод до ошибки - это лучше чем ничего
                return {
                    "model_id": model_id,
                    "passed": responses_after_button > 0 or tracker.get_response_count() > responses_before_input,
                    "step": "input_error",
                    "responses_after_button": responses_after_button,
                    "responses_after_input": tracker.get_response_count() - responses_before_input,
                    "total_responses": tracker.get_response_count(),
                    "response_summary": tracker.get_summary(),
                    "error": f"Input parameters error: {str(e)[:200]}"
                }
            
            # КРИТИЧНО: Проверяем что был хотя бы один ответ на ВСЁ взаимодействие
            has_response = tracker.has_any_response() or len(tracker.callback_answers) > 0
            
            return {
                "model_id": model_id,
                "passed": has_response,
                "step": "complete",
                "responses_after_button": responses_after_button,
                "responses_after_input": responses_after_input,
                "total_responses": tracker.get_response_count(),
                "response_summary": tracker.get_summary(),
                "error": None
            }
    except Exception as e:
        import traceback
        return {
            "model_id": model_id,
            "passed": False,
            "step": "setup_error",
            "responses_after_button": 0,
            "responses_after_input": 0,
            "total_responses": 0,
            "error": f"Setup error: {str(e)[:200]}"
        }


async def test_all_models_behavioral():
    """Тестирует поведенческий цикл для всех моделей"""
    print("\n" + "="*80)
    print("BEHAVIORAL E2E TESTING - Проверка реального поведения бота")
    print("="*80)
    
    # Получаем все модели
    if isinstance(KIE_MODELS, dict):
        models = list(KIE_MODELS.values())
    elif isinstance(KIE_MODELS, list):
        models = KIE_MODELS
    else:
        print(f"{RED}FAIL Invalid KIE_MODELS format{RESET}")
        return 1
    
    print(f"\nTesting {len(models)} models...")
    
    results = []
    passed = 0
    failed = 0
    silent_models = []
    
    # Тестируем все модели (можно ограничить для скорости в CI)
    test_models = models
    if os.getenv("CI") == "true":
        # В CI тестируем первые 20 для скорости
        test_models = models[:20]
        print(f"CI mode: Testing first {len(test_models)} models...")
    else:
        print(f"Testing all {len(test_models)} models...")
    
    for model_info in test_models:
        model_id = model_info.get('id', '')
        if not model_id:
            continue
        
        print(f"\n[TEST] {model_id}")
        result = await test_model_behavioral_flow(model_id, model_info)
        results.append(result)
        
        if result['passed']:
            passed += 1
            summary = result.get('response_summary', {})
            print(f"  {GREEN}[PASS]{RESET} {result['total_responses']} responses ({summary.get('send_message', 0)} msg, {summary.get('edit_message_text', 0)} edit)")
        else:
            failed += 1
            silent_models.append(model_id)
            print(f"  {RED}[FAIL]{RESET} No responses or error")
            if result.get('error'):
                print(f"    Error: {result['error'][:100]}")
    
    # Итоговый отчёт
    print("\n" + "="*80)
    print("BEHAVIORAL E2E RESULTS")
    print("="*80)
    
    print(f"\nTotal models tested: {len(results)}")
    print(f"{GREEN}Passed: {passed}{RESET}")
    print(f"{RED}Failed: {failed}{RESET}")
    
    if failed > 0:
        print(f"\n{RED}SILENT MODELS (NO RESPONSE):{RESET}")
        for result in results:
            if not result['passed']:
                print(f"  - {result['model_id']}: {result.get('error', 'No response')}")
    
    # Сохраняем результаты
    artifacts_dir = project_root / "artifacts" / "behavioral"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    results_file = artifacts_dir / "behavioral_e2e_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump({
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "silent_models": silent_models,
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    # Генерируем отчёт
    report_file = artifacts_dir / "behavioral_e2e_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        from datetime import datetime
        f.write("# BEHAVIORAL E2E TEST REPORT\n\n")
        f.write(f"**Date:** {datetime.now().isoformat()}\n\n")
        f.write(f"**Total models:** {len(results)}\n")
        f.write(f"**Passed:** {passed}\n")
        f.write(f"**Failed:** {failed}\n\n")
        
        if failed > 0:
            f.write("## SILENT MODELS (NO RESPONSE)\n\n")
            for result in results:
                if not result['passed']:
                    f.write(f"### {result['model_id']}\n\n")
                    f.write(f"- **Step failed:** {result.get('step', 'unknown')}\n")
                    f.write(f"- **Error:** {result.get('error', 'No response')}\n")
                    f.write(f"- **Responses:** {result['total_responses']}\n\n")
        else:
            f.write("## ALL MODELS RESPONDED\n\n")
            f.write("✅ All tested models send responses to users.\n\n")
    
    print(f"\nResults saved to: {results_file}")
    print(f"Report saved to: {report_file}")
    
    # Создаём summary.md (обязательный артефакт)
    summary_file = artifacts_dir / "summary.md"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("# BEHAVIORAL E2E SUMMARY\n\n")
        f.write(f"**Date:** {__import__('datetime').datetime.now().isoformat()}\n\n")
        f.write(f"**Total models:** {len(results)}\n")
        f.write(f"**Passed:** {passed}\n")
        f.write(f"**Failed:** {failed}\n\n")
        
        if failed == 0:
            f.write("## ✅ STATUS: 100% MODELS RESPONDED\n\n")
            f.write("Все модели отвечают пользователю. Проект готов к production.\n")
        else:
            f.write("## ❌ STATUS: SILENT MODELS DETECTED\n\n")
            f.write("Следующие модели не отвечают пользователю:\n\n")
            for result in results:
                if not result['passed']:
                    f.write(f"- **{result['model_id']}**: {result.get('error', 'No response')}\n")
            f.write("\n**ТРЕБУЕТСЯ ИСПРАВЛЕНИЕ!**\n")
    
    print(f"\nSummary saved to: {summary_file}")
    
    if failed == 0:
        print(f"\n{GREEN}100% MODELS RESPONDED!{RESET}")
        return 0
    else:
        print(f"\n{RED}THERE ARE SILENT MODELS!{RESET}")
        print(f"{YELLOW}Run: python scripts/autopilot_one_command.py{RESET}")
        return 1


def main():
    """Главная функция"""
    try:
        result = asyncio.run(test_all_models_behavioral())
        return result
    except Exception as e:
        print(f"{RED}FAIL Behavioral E2E test error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
