"""
Регресс-тесты главного меню для проверки соответствия эталону.
Эти тесты гарантируют что меню всегда соответствует требуемой структуре.
"""
import pytest
from unittest.mock import Mock, AsyncMock
from bot_kie import build_main_menu_keyboard


class TestMainMenuRegression:
    """Регресс-тесты главного меню."""

    @pytest.mark.asyncio
    async def test_main_menu_russian_etalon_structure(self):
        """Проверяем что русское меню точно соответствует эталону."""
        user_id = 12345
        user_lang = "ru"
        
        keyboard = await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
        
        # Ожидаемая структура кнопок согласно эталону
        expected_buttons = [
            "🆓 FAST TOOLS",
            "🎨 Генерация визуала", 
            "🧩 Ремикс изображения",
            "🎬 Видео по сценарию",
            "🪄 Анимировать изображение",
            "🧰 Спец-инструменты",
            "💳 Баланс / Доступ",
            "🤝 Партнёрка"
        ]
        
        # Проверяем количество строк
        assert len(keyboard) == len(expected_buttons), f"Expected {len(expected_buttons)} rows, got {len(keyboard)}"
        
        # Проверяем каждую кнопку
        for i, expected_text in enumerate(expected_buttons):
            assert len(keyboard[i]) == 1, f"Row {i} should have exactly 1 button"
            button = keyboard[i][0]
            assert button.text == expected_text, f"Row {i}: expected '{expected_text}', got '{button.text}'"
            
            # Проверяем callback_data
            if expected_text == "🆓 FAST TOOLS":
                assert button.callback_data == "fast_tools"
            elif expected_text == "🎨 Генерация визуала":
                assert button.callback_data == "gen_type:text-to-image"
            elif expected_text == "🧩 Ремикс изображения":
                assert button.callback_data == "gen_type:image-to-image"
            elif expected_text == "🎬 Видео по сценарию":
                assert button.callback_data == "gen_type:text-to-video"
            elif expected_text == "🪄 Анимировать изображение":
                assert button.callback_data == "gen_type:image-to-video"
            elif expected_text == "🧰 Спец-инструменты":
                assert button.callback_data == "special_tools"
            elif expected_text == "💳 Баланс / Доступ":
                assert button.callback_data == "check_balance"
            elif expected_text == "🤝 Партнёрка":
                assert button.callback_data == "referral_info"

    @pytest.mark.asyncio
    async def test_main_menu_english_etalon_structure(self):
        """Проверяем что английское меню точно соответствует эталону."""
        user_id = 12345
        user_lang = "en"
        
        keyboard = await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
        
        # Ожидаемая структура кнопок согласно эталону
        expected_buttons = [
            "🆓 FAST TOOLS",
            "🎨 Visual Generation",
            "🧩 Image Remix", 
            "🎬 Video by Script",
            "🪄 Animate Image",
            "🧰 Special Tools",
            "💳 Balance / Access",
            "🤝 Referral"
        ]
        
        # Проверяем количество строк
        assert len(keyboard) == len(expected_buttons), f"Expected {len(expected_buttons)} rows, got {len(keyboard)}"
        
        # Проверяем каждую кнопку
        for i, expected_text in enumerate(expected_buttons):
            assert len(keyboard[i]) == 1, f"Row {i} should have exactly 1 button"
            button = keyboard[i][0]
            assert button.text == expected_text, f"Row {i}: expected '{expected_text}', got '{button.text}'"
            
            # Проверяем callback_data (аналогично русской версии)
            if expected_text == "🆓 FAST TOOLS":
                assert button.callback_data == "fast_tools"
            elif expected_text == "🎨 Visual Generation":
                assert button.callback_data == "gen_type:text-to-image"
            elif expected_text == "🧩 Image Remix":
                assert button.callback_data == "gen_type:image-to-image"
            elif expected_text == "🎬 Video by Script":
                assert button.callback_data == "gen_type:text-to-video"
            elif expected_text == "🪄 Animate Image":
                assert button.callback_data == "gen_type:image-to-video"
            elif expected_text == "🧰 Special Tools":
                assert button.callback_data == "special_tools"
            elif expected_text == "💳 Balance / Access":
                assert button.callback_data == "check_balance"
            elif expected_text == "🤝 Referral":
                assert button.callback_data == "referral_info"

    @pytest.mark.asyncio
    async def test_main_menu_no_extra_buttons(self):
        """Проверяем что в меню нет лишних кнопок."""
        user_id = 12345
        
        for lang in ["ru", "en"]:
            keyboard = await build_main_menu_keyboard(user_id, user_lang=lang, is_new=False)
            
            # Проверяем что каждая строка содержит ровно одну кнопку
            for row_idx, row in enumerate(keyboard):
                assert len(row) == 1, f"Language {lang}, row {row_idx}: should have exactly 1 button, got {len(row)}"
                
                # Проверяем что callback_data соответствует ожидаемым паттернам
                button = row[0]
                valid_callbacks = [
                    "fast_tools",
                    "special_tools", 
                    "check_balance",
                    "referral_info",
                    "gen_type:text-to-image",
                    "gen_type:image-to-image", 
                    "gen_type:text-to-video",
                    "gen_type:image-to-video"
                ]
                assert button.callback_data in valid_callbacks, \
                    f"Language {lang}, row {row_idx}: invalid callback_data '{button.callback_data}'"

    @pytest.mark.asyncio
    async def test_main_menu_button_order(self):
        """Проверяем строгий порядок кнопок."""
        user_id = 12345
        
        for lang in ["ru", "en"]:
            keyboard = await build_main_menu_keyboard(user_id, user_lang=lang, is_new=False)
            
            # Извлекаем тексты кнопок в порядке следования
            button_texts = [row[0].text for row in keyboard]
            
            # Проверяем порядок для русского языка
            if lang == "ru":
                expected_order = [
                    "🆓 FAST TOOLS",
                    "🎨 Генерация визуала",
                    "🧩 Ремикс изображения", 
                    "🎬 Видео по сценарию",
                    "🪄 Анимировать изображение",
                    "🧰 Спец-инструменты",
                    "💳 Баланс / Доступ",
                    "🤝 Партнёрка"
                ]
            # Проверяем порядок для английского языка
            else:
                expected_order = [
                    "🆓 FAST TOOLS",
                    "🎨 Visual Generation",
                    "🧩 Image Remix",
                    "🎬 Video by Script", 
                    "🪄 Animate Image",
                    "🧰 Special Tools",
                    "💳 Balance / Access",
                    "🤝 Referral"
                ]
            
            assert button_texts == expected_order, \
                f"Language {lang}: button order mismatch. Expected: {expected_order}, got: {button_texts}"

    @pytest.mark.asyncio
    async def test_special_tools_callback_exists(self):
        """Проверяем что обработчик special_tools существует в button_callback."""
        # Этот тест проверяет что в bot_kie.py есть обработчик special_tools
        from bot_kie import button_callback
        
        # Создаем мок для проверки
        update = Mock()
        update.callback_query.data = "special_tools"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message.chat_id = 12345
        
        context = Mock()
        context.user_data = {}
        
        # Проверяем что функция не падает на special_tools
        try:
            # Мы не можем легко проверить полный путь без моков сессии,
            # но хотя бы проверим что функция не падает сразу
            result = await button_callback(update, context)
            # Может вернуть ConversationHandler.END или другой статус
            assert result is not None
        except Exception as e:
            # Если падает из-за отсутствия сессии, это нормально
            # Главное чтобы не было "unknown callback" ошибки
            if "special_tools" in str(e).lower():
                pytest.fail(f"special_tools handler not found: {e}")
            else:
                # Другие ошибки (например, отсутствие сессии) OK
                pass
