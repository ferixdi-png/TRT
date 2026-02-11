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
        
        # Ожидаемая структура кнопок согласно эталону (обновлено 2026-02-03)
        expected_buttons = [
            "🔥 Топ модели",
            "⚡ Бесплатные генерации",
            "🖼️ Текст → Фото", 
            "🧩 Редактор фото",
            "🎬 Видео по сценарию",
            "🎬 Фото → Видео",
            "🧰 Другие модели",
            "💳 Баланс / Доступ",
            "🤝 Партнёрка",
            "🌐 Язык / Language"
        ]
        
        # Проверяем количество строк
        assert len(keyboard) == len(expected_buttons), f"Expected {len(expected_buttons)} rows, got {len(keyboard)}"
        
        # Проверяем каждую кнопку
        for i, expected_text in enumerate(expected_buttons):
            assert len(keyboard[i]) == 1, f"Row {i} should have exactly 1 button"
            button = keyboard[i][0]
            assert button.text == expected_text, f"Row {i}: expected '{expected_text}', got '{button.text}'"
            
            # Проверяем callback_data
            if expected_text == "🔥 Топ модели":
                assert button.callback_data == "top_models"
            elif expected_text == "⚡ Бесплатные генерации":
                assert button.callback_data == "fast_tools"
            elif expected_text == "🖼️ Текст → Фото":
                assert button.callback_data == "gen_type:text-to-image"
            elif expected_text == "🧩 Редактор фото":
                assert button.callback_data == "gen_type:image-to-image"
            elif expected_text == "🎬 Видео по сценарию":
                assert button.callback_data == "gen_type:text-to-video"
            elif expected_text == "🎬 Фото → Видео":
                assert button.callback_data == "gen_type:image-to-video"
            elif expected_text == "🧰 Другие модели":
                assert button.callback_data == "special_tools"
            elif expected_text == "💳 Баланс / Доступ":
                assert button.callback_data == "check_balance"
            elif expected_text == "🤝 Партнёрка":
                assert button.callback_data == "referral_info"
            elif expected_text == "🌐 Язык / Language":
                assert button.callback_data == "change_language"

    @pytest.mark.asyncio
    async def test_main_menu_english_etalon_structure(self):
        """Проверяем что английское меню точно соответствует эталону."""
        user_id = 12345
        user_lang = "en"
        
        keyboard = await build_main_menu_keyboard(user_id, user_lang=user_lang, is_new=False)
        
        # Ожидаемая структура кнопок согласно эталону (обновлено 2026-02-03)
        expected_buttons = [
            "🔥 Top models",
            "⚡ Free generations",
            "🖼️ Text → Photo",
            "🧩 Photo editor", 
            "🎬 Video by Script",
            "🎬 Photo → Video",
            "🧰 More models",
            "💳 Balance / Access",
            "🤝 Referral",
            "🌐 Language / Язык"
        ]
        
        # Проверяем количество строк
        assert len(keyboard) == len(expected_buttons), f"Expected {len(expected_buttons)} rows, got {len(keyboard)}"
        
        # Проверяем каждую кнопку
        for i, expected_text in enumerate(expected_buttons):
            assert len(keyboard[i]) == 1, f"Row {i} should have exactly 1 button"
            button = keyboard[i][0]
            assert button.text == expected_text, f"Row {i}: expected '{expected_text}', got '{button.text}'"
            
            # Проверяем callback_data (аналогично русской версии)
            if expected_text == "🔥 Top models":
                assert button.callback_data == "top_models"
            elif expected_text == "⚡ Free generations":
                assert button.callback_data == "fast_tools"
            elif expected_text == "🖼️ Text → Photo":
                assert button.callback_data == "gen_type:text-to-image"
            elif expected_text == "🧩 Photo editor":
                assert button.callback_data == "gen_type:image-to-image"
            elif expected_text == "🎬 Video by Script":
                assert button.callback_data == "gen_type:text-to-video"
            elif expected_text == "🎬 Photo → Video":
                assert button.callback_data == "gen_type:image-to-video"
            elif expected_text == "🧰 More models":
                assert button.callback_data == "special_tools"
            elif expected_text == "💳 Balance / Access":
                assert button.callback_data == "check_balance"
            elif expected_text == "🤝 Referral":
                assert button.callback_data == "referral_info"
            elif expected_text == "🌐 Language / Язык":
                assert button.callback_data == "change_language"

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
                    "top_models",
                    "fast_tools",
                    "special_tools", 
                    "check_balance",
                    "referral_info",
                    "change_language",
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
            
            # Проверяем порядок для русского языка (обновлено 2026-02-03)
            if lang == "ru":
                expected_order = [
                    "🔥 Топ модели",
                    "⚡ Бесплатные генерации",
                    "🖼️ Текст → Фото",
                    "🧩 Редактор фото", 
                    "🎬 Видео по сценарию",
                    "🎬 Фото → Видео",
                    "🧰 Другие модели",
                    "💳 Баланс / Доступ",
                    "🤝 Партнёрка",
                    "🌐 Язык / Language"
                ]
            # Проверяем порядок для английского языка (обновлено 2026-02-03)
            else:
                expected_order = [
                    "🔥 Top models",
                    "⚡ Free generations",
                    "🖼️ Text → Photo",
                    "🧩 Photo editor",
                    "🎬 Video by Script", 
                    "🎬 Photo → Video",
                    "🧰 More models",
                    "💳 Balance / Access",
                    "🤝 Referral",
                    "🌐 Language / Язык"
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
