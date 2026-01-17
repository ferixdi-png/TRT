"""
Тесты главного меню бота.
Проверяет, что /start не падает и возвращает корректное меню.
"""

import re

import pytest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler

from bot_kie import _register_all_handlers_internal, button_callback, start


@pytest.mark.asyncio
async def test_start_command(harness):
    """Тест команды /start."""
    # Добавляем handler
    harness.add_handler(CommandHandler('start', start))
    
    # Обрабатываем команду
    result = await harness.process_command('/start', user_id=12345)
    
    # Проверяем результат
    assert result['success'], f"Command failed: {result.get('error')}"
    
    # Проверяем, что бот отправил сообщение
    assert len(result['outbox']['messages']) > 0, "Bot should send a message"
    
    last_message = result['outbox']['messages'][-1]
    assert 'text' in last_message, "Message should have text"
    assert last_message['text'] == "Главное меню"
    
    assert 'reply_markup' in last_message
    assert last_message['reply_markup'] is not None, "Should have reply_markup"
    keyboard = last_message['reply_markup'].inline_keyboard
    assert [button.text for row in keyboard for button in row] == [
        "БЕСПЛАТНЫЕ МОДЕЛИ",
        "Из текста в фото",
        "Из фото в фото",
        "Из текста в видео",
        "Из фото в видео",
        "Фото редактор",
        "Баланс",
        "Партнерка",
    ]


@pytest.mark.asyncio
async def test_start_command_no_crash(harness):
    """Тест, что /start не падает с исключением."""
    harness.add_handler(CommandHandler('start', start))
    
    # Обрабатываем команду несколько раз подряд
    for i in range(3):
        result = await harness.process_command('/start', user_id=12345 + i)
        assert result['success'], f"Command should not fail on attempt {i+1}"


@pytest.mark.asyncio
async def test_unknown_callback_shows_main_menu(harness):
    """Unknown callback должен возвращать главное меню."""
    harness.add_handler(CallbackQueryHandler(button_callback))

    result = await harness.process_callback('unknown_callback:123', user_id=12345)

    assert result['success']
    edited = result['outbox']['edited_messages']
    messages = result['outbox']['messages']
    assert edited or messages

    last_payload = edited[-1] if edited else messages[-1]
    assert last_payload['text'] == "Главное меню"
    keyboard = last_payload['reply_markup'].inline_keyboard
    assert [button.text for row in keyboard for button in row] == [
        "БЕСПЛАТНЫЕ МОДЕЛИ",
        "Из текста в фото",
        "Из фото в фото",
        "Из текста в видео",
        "Из фото в видео",
        "Фото редактор",
        "Баланс",
        "Партнерка",
    ]


@pytest.mark.asyncio
async def test_language_handlers_not_registered():
    """Проверяем, что language handlers не зарегистрированы."""
    application = Application.builder().token("test_token").build()
    await _register_all_handlers_internal(application)

    patterns = []

    def collect_patterns(handler):
        if isinstance(handler, CallbackQueryHandler):
            patterns.append(handler.pattern)
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                collect_patterns(entry)
            for handlers in handler.states.values():
                for entry in handlers:
                    collect_patterns(entry)
            for entry in handler.fallbacks:
                collect_patterns(entry)

    for handlers in application.handlers.values():
        for handler in handlers:
            collect_patterns(handler)

    pattern_text = " ".join(str(pattern) for pattern in patterns)
    assert re.search("language_select", pattern_text) is None
    assert re.search("change_language", pattern_text) is None
