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
    
    # Ищем кнопку FAST TOOLS
    fast_tools_found = False
    for row in keyboard_ru:
        for button in row:
            if button.callback_data == "fast_tools" and "FAST TOOLS" in button.text:
                fast_tools_found = True
                break
    
    assert fast_tools_found, "Кнопка FAST TOOLS не найдена в русском меню"
    
    # Проверяем английскую версию
    keyboard_en = await build_main_menu_keyboard(user_id, user_lang='en', is_new=False)
    
    fast_tools_found = False
    for row in keyboard_en:
        for button in row:
            if button.callback_data == "fast_tools" and "FAST TOOLS" in button.text:
                fast_tools_found = True
                break
    
    assert fast_tools_found, "Кнопка FAST TOOLS не найдена в английском меню"


@pytest.mark.asyncio
async def test_main_menu_has_all_required_buttons():
    """Проверяем что в главном меню есть все требуемые кнопки."""
    user_id = 12345
    user_lang = 'ru'
    
    keyboard = await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
    
    # Ожидаемые кнопки в порядке от эталона (из helpers.py)
    expected_buttons = [
        ("fast_tools", "🆓 FAST TOOLS"),
        ("gen_type:text-to-image", "🎨 Генерация визуала"),
        ("gen_type:image-to-image", "🧩 Ремикс изображения"),
        ("gen_type:text-to-video", "🎬 Видео по сценарию"),
        ("gen_type:image-to-video", "🪄 Анимировать изображение"),
        ("special_tools", "🧰 Спец-инструменты"),
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
    """Проверяем что callback fast_tools имеет обработчик."""
    # Упрощённый тест - проверяем наличие обработчика
    import bot_kie
    
    # Проверяем что функция free_tools_menu существует
    assert hasattr(bot_kie, 'show_free_tools_menu') or hasattr(bot_kie, 'free_tools_menu'), \
        "Обработчик free_tools_menu не найден в bot_kie"


@pytest.mark.asyncio
async def test_start_command_shows_menu():
    """Проверяем что команда /start имеет обработчик и show_main_menu работает."""
    import bot_kie
    from helpers import build_main_menu_keyboard
    
    # Проверяем что функция start существует
    assert hasattr(bot_kie, 'start'), "Функция start не найдена в bot_kie"
    assert callable(bot_kie.start), "start не является функцией"
    
    # Проверяем что меню строится корректно
    keyboard = await build_main_menu_keyboard(user_id=12345, user_lang='ru', is_new=False)
    button_texts = [button.text for row in keyboard for button in row]
    
    assert any("FAST TOOLS" in t for t in button_texts), "В меню нет кнопки FAST TOOLS"
    assert any("Генерация визуала" in t for t in button_texts), "В меню нет кнопки генерации визуала"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
