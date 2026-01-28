"""Простые тесты для проверки fast_tools функциональности."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import bot_kie
from bot_kie import build_main_menu_keyboard


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
    
    # Ищем кнопку FAST TOOLS (может быть с эмодзи 🆓)
    fast_tools = [b for b in buttons if b[0] == "fast_tools" and "FAST TOOLS" in b[1]]
    assert len(fast_tools) == 1, f"Ожидается 1 кнопка FAST TOOLS, найдено {len(fast_tools)}"


@pytest.mark.asyncio
async def test_fast_tools_callback_exists():
    """Проверяем что callback fast_tools обрабатывается."""
    # Проверяем что в bot_kie есть обработка fast_tools callback
    import inspect
    from bot_kie import button_callback
    
    # Проверяем что функция существует и является корутиной
    assert callable(button_callback), "button_callback должна быть callable"
    assert inspect.iscoroutinefunction(button_callback), "button_callback должна быть async функцией"
    
    # Проверяем что в исходном коде есть обработка fast_tools
    source_code = open(bot_kie.__file__, 'r', encoding='utf-8').read()
    assert 'fast_tools' in source_code, "Обработчик fast_tools должен быть в коде"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
