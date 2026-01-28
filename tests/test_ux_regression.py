"""
Регресс-тесты для UX аудита меню.

Проверяют что главное меню и все ветки соответствуют эталону.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot_kie import show_main_menu
from helpers import build_main_menu_keyboard


class TestUXRegression:
    """Регресс-тесты UX меню."""

    @pytest.mark.asyncio
    async def test_main_menu_structure_exact_match(self):
        """Проверяет точное соответствие главного меню эталону."""
        user_id = 12345
        user_lang = "ru"
        
        # Функция build_main_menu_keyboard статическая, не требует моков
        keyboard = await build_main_menu_keyboard(
            user_id=user_id,
            user_lang=user_lang
        )
        
        # Проверяем количество кнопок
        assert len(keyboard) == 8, f"Ожидается 8 кнопок, получено {len(keyboard)}"
        
        # Проверяем точный порядок и текст кнопок
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
        
        actual_buttons = []
        for row in keyboard:
            assert len(row) == 1, f"Каждая строка должна содержать 1 кнопку, получено {len(row)}"
            actual_buttons.append(row[0].text)
        
        assert actual_buttons == expected_buttons, f"Кнопки не соответствуют эталону:\nОжидается: {expected_buttons}\nПолучено: {actual_buttons}"
        
        # Проверяем callback_data
        expected_callbacks = [
            "fast_tools",
            "gen_type:text-to-image",
            "gen_type:image-to-image", 
            "gen_type:text-to-video",
            "gen_type:image-to-video",  # ПРОБЛЕМА: дублируется!
            "special_tools",
            "check_balance",
            "referral_info"
        ]
        
        actual_callbacks = []
        for row in keyboard:
            actual_callbacks.append(row[0].callback_data)
        
        assert actual_callbacks == expected_callbacks, f"Callback данные не соответствуют эталону:\nОжидается: {expected_callbacks}\nПолучено: {actual_callbacks}"

    def test_main_menu_structure_english(self):
        """Проверяет структуру меню на английском."""
        user_lang = "en"
        
        keyboard = build_main_menu_keyboard(user_lang)
        
        # Проверяем количество кнопок
        assert len(keyboard) == 8, f"Ожидается 8 кнопок, получено {len(keyboard)}"
        
        # Проверяем английские названия
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
        
        actual_buttons = []
        for row in keyboard:
            actual_buttons.append(row[0].text)
        
        assert actual_buttons == expected_buttons, f"Английские кнопки не соответствуют эталону:\nОжидается: {expected_buttons}\nПолучено: {actual_buttons}"

    def test_no_extra_buttons_in_main_menu(self):
        """Проверяет что нет лишних кнопок в главном меню."""
        user_lang = "ru"
        
        keyboard = build_main_menu_keyboard(user_lang)
        
        # Проверяем что нет кнопок Audio/Музыка, Текст/Перевод и т.д.
        forbidden_buttons = [
            "Аудио", "Музыка", "Текст", "Перевод", 
            "Улучшение качества", "Другие инструменты"
        ]
        
        actual_buttons = []
        for row in keyboard:
            actual_buttons.append(row[0].text)
        
        for forbidden in forbidden_buttons:
            assert not any(forbidden in button for button in actual_buttons), f"Найдена запрещенная кнопка: {forbidden}"

    @pytest.mark.asyncio
    async def test_show_main_menu_function_exists(self):
        """Проверяет что функция show_main_menu работает."""
        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_user.language_code = "ru"
        update.effective_chat.id = 67890
        update.update_id = "test_update"
        
        context = MagicMock()
        context.user_data = {}
        
        # Мокаем зависимости
        with patch('bot_kie.ensure_correlation_id', return_value="test_corr"):
            with patch('bot_kie._safe_menu_renderer.get_if_duplicate', return_value=None):
                with patch('bot_kie._is_storage_degraded', return_value=False):
                    with patch('bot_kie._get_menu_dep_cache', return_value={}):
                        with patch('bot_kie._schedule_menu_dependency_refresh'):
                            with patch('bot_kie.user_sessions') as mock_sessions:
                                mock_session = {}
                                mock_sessions.ensure.return_value = mock_session
                                mock_sessions.__contains__ = lambda self, user_id: False
                                mock_sessions.__getitem__ = lambda self, user_id: mock_session
                                
                                with patch('bot_kie._build_menu_payload') as mock_build:
                                    mock_build.return_value = (
                                        MagicMock(),  # keyboard
                                        "test header text"  # header_text
                                    )
                                    
                                    with patch('bot_kie._send_menu_message') as mock_send:
                                        mock_send.return_value = {"message_id": 123}
                                        
                                        result = await show_main_menu(
                                            update, 
                                            context, 
                                            source="test"
                                        )
                                        
                                        # Проверяем что меню было отправлено
                                        mock_send.assert_called_once()
                                        assert result is not None

    def test_fast_tools_callback_unique(self):
        """Проверяет что у FAST TOOLS уникальный callback."""
        user_lang = "ru"
        keyboard = build_main_menu_keyboard(user_lang)
        
        # Находим кнопку FAST TOOLS
        fast_tools_button = None
        for row in keyboard:
            if "FAST TOOLS" in row[0].text:
                fast_tools_button = row[0]
                break
        
        assert fast_tools_button is not None, "Кнопка FAST TOOLS не найдена"
        assert fast_tools_button.callback_data == "fast_tools", f"Неверный callback для FAST TOOLS: {fast_tools_button.callback_data}"

    def test_special_tools_callback_exists(self):
        """Проверяет что у Спец-инструментов есть callback."""
        user_lang = "ru"
        keyboard = build_main_menu_keyboard(user_lang)
        
        # Находим кнопку Спец-инструменты
        special_tools_button = None
        for row in keyboard:
            if "Спец-инструменты" in row[0].text:
                special_tools_button = row[0]
                break
        
        assert special_tools_button is not None, "Кнопка Спец-инструменты не найдена"
        assert special_tools_button.callback_data == "special_tools", f"Неверный callback для Спец-инструментов: {special_tools_button.callback_data}"

    @pytest.mark.asyncio
    async def test_duplicate_callback_detection(self):
        """Проверяет что дублируются callback'и (проблема с Анимировать изображение)."""
        user_id = 12345
        user_lang = "ru"
        
        keyboard = await build_main_menu_keyboard(
            user_id=user_id,
            user_lang=user_lang
        )
        
        # Собираем все callback_data
        callbacks = []
        for row in keyboard:
            callbacks.append(row[0].callback_data)
        
        # Отладочный вывод
        print(f"Callbacks: {callbacks}")
        
        # Проверяем на дубликаты
        unique_callbacks = set(callbacks)
        duplicates = [cb for cb in callbacks if callbacks.count(cb) > 1]
        
        # Эта тест должен показать проблему с image-to-video
        assert len(duplicates) > 0, f"Ожидались дубликаты callback'ов, но не найдено. Callbacks: {callbacks}"
        assert "gen_type:image-to-video" in duplicates, "Проблема с дублированием image-to-video не найдена"

    @pytest.mark.asyncio 
    async def test_welcome_text_structure(self):
        """Проверяет структуру приветственного текста."""
        from bot_kie import _build_welcome_text_and_details
        
        user_id = 12345
        user_lang = "ru"
        correlation_id = "test_corr"
        
        # Мокаем зависимости
        with patch('bot_kie.get_user_language_async', return_value="ru"):
            with patch('bot_kie.get_is_admin', return_value=False):
                with patch('bot_kie.get_user_free_generations_remaining', return_value=5):
                    with patch('bot_kie.get_models_sync', return_value=74):
                        with patch('bot_kie.get_generation_types', return_value=4):
                            with patch('bot_kie.get_categories_from_registry', return_value=["Фото", "Видео"]):
                                with patch('bot_kie.get_online_users_count', return_value=10):
                                    
                                    header_text, details_text = await _build_welcome_text_and_details(
                                        user_id=user_id,
                                        user_lang=user_lang,
                                        correlation_id=correlation_id
                                    )
                                    
                                    # Проверяем ключевые элементы приветствия
                                    assert "Привет!" in header_text
                                    assert "FERIXDI AI" in header_text
                                    assert "Ultra Creative Suite" in header_text
                                    assert "маркетинга / SMM / арбитража" in header_text
                                    assert "Спец-раздел" in header_text
                                    assert "Как работать" in header_text
                                    assert "Выберите раздел" in header_text

    def test_menu_compactness(self):
        """Проверяет что меню компактное и без лишних элементов."""
        user_lang = "ru"
        keyboard = build_main_menu_keyboard(user_lang)
        
        # Проверяем что ровно 8 кнопок
        assert len(keyboard) == 8, f"Меню должно содержать ровно 8 кнопок, получено {len(keyboard)}"
        
        # Проверяем что каждая строка содержит ровно 1 кнопку
        for i, row in enumerate(keyboard):
            assert len(row) == 1, f"Строка {i} должна содержать 1 кнопку, содержит {len(row)}"
        
        # Проверяем что нет многоуровневых кнопок
        for row in keyboard:
            button = row[0]
            assert not button.callback_data.startswith("category:"), "Категории не должны быть в главном меню"
            assert not button.callback_data.startswith("all_models"), "Все модели не должны быть в главном меню"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
