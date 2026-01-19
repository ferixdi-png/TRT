"""
Тесты главного меню бота.
Проверяет, что /start не падает и возвращает корректное меню.
"""

import re

import pytest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler

import bot_kie
from bot_kie import (
    TELEGRAM_TEXT_LIMIT,
    _register_all_handlers_internal,
    button_callback,
    start,
)


@pytest.mark.asyncio
async def test_start_command(harness):
    """Тест команды /start."""
    # Добавляем handler
    harness.add_handler(CommandHandler('start', start))
    
    # Обрабатываем команду
    result = await harness.process_command('/start', user_id=12345)
    
    # Проверяем результат
    assert result['success'], f"Command failed: {result.get('error')}"
    
    # Проверяем, что бот отправил одно сообщение
    assert len(result['outbox']['messages']) == 1, "Bot should send a single welcome message"
    
    messages = result['outbox']['messages']
    assert messages, "Bot should send a message"
    header_message = messages[0]
    assert 'text' in header_message, "Message should have text"
    assert "Привет" in header_message['text'] or "Welcome" in header_message['text']
    assert 'reply_markup' in header_message
    assert header_message['reply_markup'] is not None, "Should have reply_markup"
    keyboard = header_message['reply_markup'].inline_keyboard
    assert [button.text for row in keyboard for button in row] == [
        "БЕСПЛАТНЫЕ МОДЕЛИ",
        "Из текста в фото",
        "Из фото в фото",
        "Из текста в видео",
        "Из фото в видео",
        "Баланс",
        "Партнерка",
    ]
    assert "Версия" not in header_message['text']
    assert "Что нового" not in header_message['text']


@pytest.mark.asyncio
async def test_start_command_no_crash(harness):
    """Тест, что /start не падает с исключением."""
    harness.add_handler(CommandHandler('start', start))
    
    # Обрабатываем команду несколько раз подряд
    for i in range(3):
        result = await harness.process_command('/start', user_id=12345 + i)
        assert result['success'], f"Command should not fail on attempt {i+1}"


@pytest.mark.asyncio
async def test_start_long_welcome_splits_chunks(harness, monkeypatch):
    """Details блоки не должны отправляться отдельными сообщениями."""
    header_text = "<b>ДОБРО ПОЖАЛОВАТЬ</b>"
    long_text = "<b>Детали</b>\n\n" + ("A" * (TELEGRAM_TEXT_LIMIT + 500))

    async def fake_build_main_menu_sections(update):
        return header_text, long_text

    monkeypatch.setattr(bot_kie, "_build_main_menu_sections", fake_build_main_menu_sections)

    harness.add_handler(CommandHandler('start', start))

    result = await harness.process_command('/start', user_id=12345)

    assert result['success'], f"Command failed: {result.get('error')}"
    messages = result['outbox']['messages']
    assert len(messages) == 1, "Main menu should not send extra detail cards"
    assert len(messages[0]['text']) <= TELEGRAM_TEXT_LIMIT
    assert messages[0]['reply_markup'] is not None


@pytest.mark.asyncio
async def test_unknown_callback_shows_main_menu(harness):
    """Unknown callback должен возвращать главное меню."""
    harness.add_handler(CallbackQueryHandler(button_callback))

    result = await harness.process_callback('unknown_callback:123', user_id=12345)

    assert result['success']
    edited = result['outbox']['edited_messages']
    messages = result['outbox']['messages']
    assert edited or messages

    payloads = edited + messages
    assert any("Привет" in payload["text"] or "Welcome" in payload["text"] for payload in payloads)
    header_payload = next(payload for payload in payloads if payload.get("reply_markup"))
    keyboard = header_payload['reply_markup'].inline_keyboard
    assert [button.text for row in keyboard for button in row] == [
        "БЕСПЛАТНЫЕ МОДЕЛИ",
        "Из текста в фото",
        "Из фото в фото",
        "Из текста в видео",
        "Из фото в видео",
        "Баланс",
        "Партнерка",
    ]
    assert all("Версия" not in message['text'] for message in payloads)
    assert all("Что нового" not in message['text'] for message in payloads)


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
