"""Тесты для проверки структуры главного меню и стартового сообщения."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import CommandHandler
import bot_kie
from helpers import build_main_menu_keyboard


@pytest.mark.asyncio
async def test_main_menu_has_fast_tools_button():
    """Проверяем что в главном меню есть кнопка FREE FAST TOOLS."""
    user_id = 12345
    
    # Проверяем русскую версию
    keyboard_ru = await build_main_menu_keyboard(user_id, user_lang='ru', is_new=False)
    
    # Ищем кнопку FREE FAST TOOLS
    fast_tools_found = False
    for row in keyboard_ru:
        for button in row:
            if button.callback_data == "fast_tools" and "FREE FAST TOOLS" in button.text:
                fast_tools_found = True
                break
    
    assert fast_tools_found, "Кнопка FREE FAST TOOLS не найдена в русском меню"
    
    # Проверяем английскую версию
    keyboard_en = await build_main_menu_keyboard(user_id, user_lang='en', is_new=False)
    
    fast_tools_found = False
    for row in keyboard_en:
        for button in row:
            if button.callback_data == "fast_tools" and "FREE FAST TOOLS" in button.text:
                fast_tools_found = True
                break
    
    assert fast_tools_found, "Кнопка FREE FAST TOOLS не найдена в английском меню"


@pytest.mark.asyncio
async def test_main_menu_has_all_required_buttons():
    """Проверяем что в главном меню есть все требуемые кнопки."""
    user_id = 12345
    user_lang = 'ru'
    
    keyboard = await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
    
    # Ожидаемые кнопки в порядке от эталона
    expected_buttons = [
        ("fast_tools", "⚡ FREE FAST TOOLS"),
        ("gen_type:text-to-image", " Генерация визуала"),
        ("gen_type:image-to-image", "🧩 Ремикс изображения"),
        ("gen_type:text-to-video", "🎬 Видео по сценарию"),
        ("gen_type:image-to-video", "🎞️ Анимировать изображение"),
        ("gen_type:audio-to-audio", "🎵 Аудио/Музыка"),
        ("gen_type:text-to-text", "✍️ Текст/Перевод"),
        ("gen_type:upscale", "🖼️ Улучшение качества"),
        ("check_balance", "💳 Баланс / Доступ"),
        ("referral_info", "🤝 Партнёрка")
    ]
    
    # Проверяем наличие всех кнопок
    actual_buttons = []
    for row in keyboard:
        for button in row:
            actual_buttons.append((button.callback_data, button.text))
    
    for expected_callback, expected_text in expected_buttons:
        found = any(
            callback == expected_callback and text == expected_text
            for callback, text in actual_buttons
        )
        assert found, f"Кнопка {expected_text} ({expected_callback}) не найдена в меню"
    
    # Проверяем что нет лишних кнопок
    assert len(actual_buttons) == len(expected_buttons), f"Количество кнопок не совпадает. Ожидается {len(expected_buttons)}, найдено {len(actual_buttons)}"


@pytest.mark.asyncio
async def test_fast_tools_handler_exists():
    """Проверяем что обработчик fast_tools зарегистрирован."""
    # Проверяем наличие в entry_points ConversationHandler
    from bot_kie import _register_all_handlers_internal
    
    # Создаем мок application
    mock_app = MagicMock()
    
    # Вызываем функцию регистрации
    await _register_all_handlers_internal(mock_app)
    
    # Проверяем что был вызван add_handler
    assert mock_app.add_handler.called, "add_handler не был вызван"
    
    # Ищем вызовы с ConversationHandler
    conversation_handler_calls = [
        call for call in mock_app.add_handler.call_args_list
        if len(call[0]) > 0 and hasattr(call[0][0], 'entry_points')
    ]
    
    assert len(conversation_handler_calls) > 0, "ConversationHandler не зарегистрирован"
    
    # Проверяем entry_points в ConversationHandler
    conv_handler = conversation_handler_calls[0][0][0]
    entry_points = conv_handler.entry_points
    
    # Ищем обработчик fast_tools
    fast_tools_handler_found = False
    for handler in entry_points:
        if hasattr(handler, 'pattern') and 'fast_tools' in str(handler.pattern):
            fast_tools_handler_found = True
            break
    
    assert fast_tools_handler_found, "Обработчик fast_tools не найден в entry_points"


@pytest.mark.asyncio
async def test_fast_tools_callback_routing():
    """Проверяем что callback fast_tools обрабатывается корректно."""
    from tests.conftest import PTBHarness
    
    harness = PTBHarness()
    await harness.setup()
    
    # Регистрируем обработчики
    from bot_kie import _register_all_handlers_internal
    await _register_all_handlers_internal(harness.application)
    
    # Добавляем CommandHandler для start
    from bot_kie import start
    harness.application.add_handler(CommandHandler("start", start))
    
    user_id = 3001
    result = await harness.process_callback("fast_tools", user_id=user_id)
    
    assert result["success"], f"Ошибка обработки fast_tools: {result.get('error', 'Unknown error')}"
    assert result["outbox"]["messages"], "Нет ответного сообщения"
    
    # Проверяем что в ответе есть информация о FREE FAST TOOLS
    message = result["outbox"]["messages"][0]
    assert "FREE FAST TOOLS" in message["text"], "В ответе нет упоминания FREE FAST TOOLS"


@pytest.mark.asyncio
async def test_start_command_shows_menu():
    """Проверяем что команда /start показывает главное меню."""
    from tests.conftest import PTBHarness
    
    harness = PTBHarness()
    await harness.setup()
    
    # Регистрируем обработчики
    from bot_kie import _register_all_handlers_internal
    await _register_all_handlers_internal(harness.application)
    
    # Добавляем CommandHandler для start
    from bot_kie import start
    harness.application.add_handler(CommandHandler("start", start))
    
    user_id = 3002
    result = await harness.process_command("/start", user_id=user_id)
    
    assert result["success"], f"Ошибка обработки /start: {result.get('error', 'Unknown error')}"
    assert result["outbox"]["messages"], "Нет ответного сообщения"
    
    # Проверяем что в ответе есть приветствие и меню
    message = result["outbox"]["messages"][0]
    assert "FERIXDI AI" in message["text"], "В ответе нет приветствия FERIXDI AI"
    assert message["reply_markup"], "В ответе нет клавиатуры меню"
    
    # Проверяем наличие кнопок в клавиатуре
    keyboard = message["reply_markup"].inline_keyboard
    button_texts = [button.text for row in keyboard for button in row]
    
    assert "⚡ FREE FAST TOOLS" in button_texts, "В меню нет кнопки FREE FAST TOOLS"
    assert " Генерация визуала" in button_texts, "В меню нет кнопки генерации визуала"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
