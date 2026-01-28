"""
Регресс-тесты для UX аудита меню.

Проверяют что главное меню и все ветки соответствуют эталону.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot_kie import show_main_menu, build_main_menu_keyboard


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

    @pytest.mark.asyncio
    async def test_main_menu_structure_english(self):
        """Проверяет структуру меню на английском."""
        user_id = 12345
        user_lang = "en"
        
        keyboard = await build_main_menu_keyboard(user_id=user_id, user_lang=user_lang)
        
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

    @pytest.mark.asyncio
    async def test_no_extra_buttons_in_main_menu(self):
        """Проверяет что нет лишних кнопок в главном меню."""
        user_id = 12345
        user_lang = "ru"
        
        keyboard = await build_main_menu_keyboard(user_id=user_id, user_lang=user_lang)
        
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
        """Проверяет что функция show_main_menu существует и имеет правильную сигнатуру."""
        import inspect
        
        # Проверяем что функция существует и является корутиной
        assert callable(show_main_menu), "show_main_menu должна быть callable"
        assert inspect.iscoroutinefunction(show_main_menu), "show_main_menu должна быть async функцией"

    @pytest.mark.asyncio
    async def test_fast_tools_callback_unique(self):
        """Проверяет что у FAST TOOLS уникальный callback."""
        user_id = 12345
        user_lang = "ru"
        keyboard = await build_main_menu_keyboard(user_id=user_id, user_lang=user_lang)
        
        # Находим кнопку FAST TOOLS
        fast_tools_button = None
        for row in keyboard:
            if "FAST TOOLS" in row[0].text:
                fast_tools_button = row[0]
                break
        
        assert fast_tools_button is not None, "Кнопка FAST TOOLS не найдена"
        assert fast_tools_button.callback_data == "fast_tools", f"Неверный callback для FAST TOOLS: {fast_tools_button.callback_data}"

    @pytest.mark.asyncio
    async def test_special_tools_callback_exists(self):
        """Проверяет что у Спец-инструментов есть callback."""
        user_id = 12345
        user_lang = "ru"
        keyboard = await build_main_menu_keyboard(user_id=user_id, user_lang=user_lang)
        
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
        
        # Проверяем что дубликатов НЕТ (это правильное поведение)
        assert len(duplicates) == 0, f"Найдены дубликаты callback'ов: {duplicates}"
        assert len(unique_callbacks) == 8, f"Ожидается 8 уникальных callback'ов, получено {len(unique_callbacks)}"

    @pytest.mark.asyncio 
    async def test_welcome_text_contains_key_elements(self):
        """Проверяет что приветственный текст содержит ключевые элементы."""
        # Эталонный текст приветствия должен содержать ключевые элементы
        # Проверяем через константу или строку в bot_kie.py
        import bot_kie
        
        # Ищем текст приветствия в исходном коде модуля
        source_code = open(bot_kie.__file__, 'r', encoding='utf-8').read()
        
        # Проверяем ключевые элементы приветствия в исходном коде
        assert "FERIXDI AI" in source_code, "Отсутствует название бота в коде"
        assert "Ultra Creative Suite" in source_code, "Отсутствует описание в коде"
        assert "маркетинг" in source_code.lower() or "smm" in source_code.lower(), "Отсутствует упоминание маркетинга/SMM"
        assert "Спец-раздел" in source_code or "Special" in source_code, "Отсутствует упоминание спец-раздела"

    @pytest.mark.asyncio
    async def test_menu_compactness(self):
        """Проверяет что меню компактное и без лишних элементов."""
        user_id = 12345
        user_lang = "ru"
        keyboard = await build_main_menu_keyboard(user_id=user_id, user_lang=user_lang)
        
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
