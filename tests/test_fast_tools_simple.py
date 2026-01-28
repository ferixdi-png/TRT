"""Простые тесты для проверки fast_tools функциональности."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import bot_kie
from helpers import build_main_menu_keyboard


@pytest.mark.asyncio
async def test_fast_tools_button_in_menu():
    """Проверяем что кнопка FREE FAST TOOLS есть в меню."""
    user_id = 12345
    
    # Проверяем русскую версию
    keyboard = await build_main_menu_keyboard(user_id, user_lang='ru', is_new=False)
    
    # Преобразуем в плоский список для проверки
    buttons = []
    for row in keyboard:
        for button in row:
            buttons.append((button.callback_data, button.text))
    
    # Ищем кнопку FREE FAST TOOLS
    fast_tools = [b for b in buttons if b[0] == "fast_tools" and "FREE FAST TOOLS" in b[1]]
    assert len(fast_tools) == 1, f"Ожидается 1 кнопка FREE FAST TOOLS, найдено {len(fast_tools)}"


@pytest.mark.asyncio
async def test_fast_tools_handler_logic():
    """Проверяем логику обработки fast_tools."""
    from bot_kie import _button_callback_impl
    from telegram import Update, CallbackQuery
    
    # Создаем моки
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "fast_tools"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.update_id = 1
    
    context = MagicMock()
    context.user_data = {}
    
    # Мокаем зависимости
    with patch('bot_kie.get_user_language', return_value='ru'), \
         patch('bot_kie.reset_session_on_navigation'), \
         patch('bot_kie.get_models_static_only', return_value=[
             {'id': 'model1', 'name': 'Model 1', 'emoji': '🤖'},
             {'id': 'model2', 'name': 'Model 2', 'emoji': '🎨'}
         ]), \
         patch('bot_kie.get_from_price_value', side_effect=[1, 2]), \
         patch('bot_kie.get_user_free_generations_remaining', return_value=5), \
         patch('bot_kie.t', return_value='Назад'):
        
        # Вызываем обработчик
        result = await _button_callback_impl(update, context)
        
        # Проверяем что был вызван answer
        update.callback_query.answer.assert_called_once()
        
        # Проверяем что было вызвано edit_message_text
        update.callback_query.edit_message_text.assert_called_once()
        
        # Проверяем содержимое сообщения
        call_args = update.callback_query.edit_message_text.call_args
        text = call_args[0][0]  # Первый позиционный аргумент
        assert "FREE FAST TOOLS" in text
        assert "Бесплатные генерации: 5 шт." in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
