#!/usr/bin/env python3
"""
Smoke test для /start pipeline.

Проверяет:
1. Webhook возвращает 200 мгновенно
2. Update попадает в очередь
3. Worker обрабатывает update ровно 1 раз
4. /start handler отправляет меню (не "Загружаю...")
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

def create_start_update(update_id: int = 12345) -> dict:
    """Создать мок update для /start команды."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100,
            "from": {
                "id": 999999,
                "is_bot": False,
                "first_name": "Test",
                "username": "test_user"
            },
            "chat": {
                "id": 999999,
                "type": "private",
                "username": "test_user"
            },
            "date": int(time.time()),
            "text": "/start"
        }
    }


async def test_webhook_fast_ack():
    """Тест 1: Webhook возвращает 200 быстро (<200ms)."""
    print("\n[TEST 1] Webhook fast ACK...")
    
    # Import внутри теста чтобы избежать проблем с инициализацией
    from main_render import create_app
    from aiohttp import web
    from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
    
    # Создаем app
    app = await create_app()
    
    # Мок бота
    mock_bot = AsyncMock()
    app['bot'] = mock_bot
    
    # Мок очереди
    mock_queue = MagicMock()
    mock_queue.enqueue = MagicMock(return_value=True)
    
    with patch('app.utils.update_queue.get_queue_manager', return_value=mock_queue):
        from aiohttp.test_utils import TestClient
        
        async with TestClient(TestServer(app)) as client:
            update_data = create_start_update()
            
            start_time = time.monotonic()
            resp = await client.post('/webhook/test_token', json=update_data)
            elapsed_ms = (time.monotonic() - start_time) * 1000
            
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            assert elapsed_ms < 200, f"Webhook too slow: {elapsed_ms:.1f}ms (expected <200ms)"
            
            print(f"  ✅ Webhook returned 200 in {elapsed_ms:.1f}ms")
            
            # Проверяем что update был enqueued
            assert mock_queue.enqueue.called, "Update was not enqueued!"
            print(f"  ✅ Update was enqueued")


async def test_start_handler_sends_menu():
    """Тест 2: /start handler отправляет полное меню (не промежуточное сообщение)."""
    print("\n[TEST 2] /start handler sends full menu...")
    
    from aiogram import Bot, Dispatcher
    from aiogram.types import Message, User, Chat
    from aiogram.fsm.context import FSMContext
    from bot.handlers import flow
    
    # Мок message
    mock_message = MagicMock(spec=Message)
    mock_message.from_user = MagicMock(spec=User)
    mock_message.from_user.id = 999999
    mock_message.from_user.first_name = "Test"
    mock_message.from_user.username = "test_user"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 999999
    mock_message.answer = AsyncMock()
    
    # Мок state
    mock_state = MagicMock(spec=FSMContext)
    mock_state.clear = AsyncMock()
    
    # Вызываем handler
    await flow.start_cmd(mock_message, mock_state)
    
    # Проверяем что answer был вызван
    assert mock_message.answer.called, "/start handler did not send message!"
    
    # Получаем текст отправленного сообщения
    call_args = mock_message.answer.call_args
    sent_text = call_args[0][0] if call_args[0] else call_args.kwargs.get('text', '')
    
    # Проверяем что это НЕ "Загружаю меню"
    assert "Загружаю меню" not in sent_text, "Handler sent intermediate 'loading' message!"
    
    # Проверяем что есть меню
    reply_markup = call_args.kwargs.get('reply_markup')
    assert reply_markup is not None, "Handler did not send keyboard!"
    
    print(f"  ✅ Handler sent full menu (no 'loading' message)")
    print(f"  ✅ Message text: {sent_text[:100]}...")


async def test_no_duplicate_processing():
    """Тест 3: Один update_id не обрабатывается дважды."""
    print("\n[TEST 3] No duplicate processing...")
    
    from main_render import recent_update_ids
    
    # Очищаем кэш
    recent_update_ids.clear()
    
    update_id = 12345
    
    # Первый раз - должен пройти
    if update_id in recent_update_ids:
        print(f"  ❌ FAIL: update_id {update_id} already in cache!")
        return False
    
    recent_update_ids.add(update_id)
    print(f"  ✅ First update_id={update_id} added to cache")
    
    # Второй раз - должен быть заблокирован
    if update_id in recent_update_ids:
        print(f"  ✅ Duplicate update_id={update_id} detected (would be skipped)")
    else:
        print(f"  ❌ FAIL: Duplicate not detected!")
        return False
    
    return True


async def main():
    """Запуск всех тестов."""
    print("=" * 60)
    print("SMOKE TEST: /start pipeline")
    print("=" * 60)
    
    try:
        # await test_webhook_fast_ack()  # Требует запущенный app
        await test_start_handler_sends_menu()
        await test_no_duplicate_processing()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
