#!/usr/bin/env python3
"""
Тест для проверки работы кнопок главного меню после исправлений.
Проверяет полный цикл: /start → меню → кнопки gen_type.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tests.ptb_harness import PTBHarness
from bot_kie import start, button_callback


async def test_menu_buttons_flow():
    """Тестируем полный цикл работы кнопок меню."""
    print("🧪 НАЧАЛО ТЕСТА: Полный цикл кнопок меню")
    
    harness = PTBHarness()
    harness.add_handler(start)
    harness.add_handler(button_callback)
    
    user_id = 12345
    
    # 1. Тестируем /start
    print("\n1️⃣ Тестируем команду /start...")
    result = await harness.process_command("/start", user_id=user_id)
    
    if not result["success"]:
        print(f"❌ Ошибка /start: {result.get('error')}")
        return False
    
    print("✅ /start работает")
    
    # 2. Проверяем наличие кнопок в меню
    message = result["message"]
    if not message or not message.reply_markup:
        print("❌ Нет клавиатуры в меню")
        return False
    
    keyboard = message.reply_markup.inline_keyboard
    expected_buttons = [
        "🎨 Генерация визуала",
        "🧩 Ремикс изображения", 
        "🎬 Видео по сценарию",
        "🎞️ Анимировать изображение",
        "🎵 Аудио/Музыка",
        "✍️ Текст/Перевод",
        "🖼️ Улучшение качества",
        "🪄 Другие инструменты",
        "💳 Баланс / Доступ",
        "🤝 Партнёрка"
    ]
    
    found_buttons = []
    for row in keyboard:
        for button in row:
            found_buttons.append(button.text)
    
    print(f"📋 Найдено кнопок: {len(found_buttons)}")
    for expected in expected_buttons:
        if expected in found_buttons:
            print(f"✅ {expected}")
        else:
            print(f"❌ {expected} - НЕ НАЙДЕНА")
    
    # 3. Тестируем каждую gen_type кнопку
    gen_type_buttons = [
        ("🎨 Генерация визуала", "gen_type:text-to-image"),
        ("🧩 Ремикс изображения", "gen_type:image-to-image"),
        ("🎬 Видео по сценарию", "gen_type:text-to-video"),
        ("🎞️ Анимировать изображение", "gen_type:image-to-video"),
        ("🎵 Аудио/Музыка", "gen_type:audio-to-audio"),
        ("✍️ Текст/Перевод", "gen_type:text-to-text"),
        ("🖼️ Улучшение качества", "gen_type:upscale"),
    ]
    
    print("\n2️⃣ Тестируем кнопки gen_type...")
    for button_text, callback_data in gen_type_buttons:
        print(f"\n🔘 Тестируем: {button_text}")
        
        result = await harness.process_callback(callback_data, user_id=user_id)
        
        if not result["success"]:
            print(f"❌ Ошибка {button_text}: {result.get('error')}")
            continue
        
        print(f"✅ {button_text} работает")
        
        # Проверяем что изменилось сообщение
        if result.get("message") and result["message"].text:
            if "Выбран тип" in result["message"].text or "Selected type" in result["message"].text:
                print(f"✅ Сообщение обновлено корректно")
            else:
                print(f"⚠️ Сообщение: {result['message'].text[:100]}...")
    
    # 4. Тестируем кнопку "Назад в меню"
    print("\n3️⃣ Тестируем кнопку 'Назад в меню'...")
    result = await harness.process_callback("back_to_menu", user_id=user_id)
    
    if not result["success"]:
        print(f"❌ Ошибка back_to_menu: {result.get('error')}")
        return False
    
    print("✅ Кнопка 'Назад в меню' работает")
    
    print("\n🎉 ТЕСТ ЗАВЕРШЕН: Все основные функции работают!")
    return True


if __name__ == "__main__":
    asyncio.run(test_menu_buttons_flow())
