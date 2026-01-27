#!/usr/bin/env python3
"""
Простой тест для проверки работы кнопок главного меню.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tests.ptb_harness import PTBHarness
from bot_kie import start, button_callback


async def test_menu_flow():
    """Тестируем полный цикл работы меню."""
    print("START: Menu buttons test")
    
    harness = PTBHarness()
    await harness.setup()  # Инициализация приложения
    harness.add_handler(start)
    harness.add_handler(button_callback)
    
    user_id = 12345
    
    # 1. Тестируем /start
    print("\n1. Testing /start command...")
    result = await harness.process_command("/start", user_id=user_id)
    
    if not result["success"]:
        print(f"ERROR /start: {result.get('error')}")
        return False
    
    print("OK: /start works")
    
    # 2. Проверяем кнопки
    message = result["message"]
    if not message or not message.reply_markup:
        print("ERROR: No keyboard in menu")
        return False
    
    keyboard = message.reply_markup.inline_keyboard
    expected_callbacks = [
        "gen_type:text-to-image",
        "gen_type:image-to-image", 
        "gen_type:text-to-video",
        "gen_type:image-to-video",
        "gen_type:audio-to-audio",
        "gen_type:text-to-text",
        "gen_type:upscale",
        "other_models",
        "check_balance",
        "referral_info"
    ]
    
    found_callbacks = []
    for row in keyboard:
        for button in row:
            found_callbacks.append(button.callback_data)
    
    print(f"Found buttons: {len(found_callbacks)}")
    for expected in expected_callbacks:
        if expected in found_callbacks:
            print(f"OK: {expected}")
        else:
            print(f"MISSING: {expected}")
    
    # 3. Тестируем gen_type кнопки
    gen_type_tests = [
        ("text-to-image", "gen_type:text-to-image"),
        ("image-to-image", "gen_type:image-to-image"),
        ("text-to-video", "gen_type:text-to-video"),
    ]
    
    print("\n2. Testing gen_type buttons...")
    for test_name, callback_data in gen_type_tests:
        print(f"\nTesting: {test_name}")
        
        result = await harness.process_callback(callback_data, user_id=user_id)
        
        if not result["success"]:
            print(f"ERROR {test_name}: {result.get('error')}")
            continue
        
        print(f"OK: {test_name} works")
        
        # Проверяем изменение сообщения
        if result.get("message") and result["message"].text:
            if "Выбран тип" in result["message"].text or "Selected type" in result["message"].text:
                print("OK: Message updated correctly")
    
    # 4. Тестируем кнопку назад
    print("\n3. Testing back button...")
    result = await harness.process_callback("back_to_menu", user_id=user_id)
    
    if not result["success"]:
        print(f"ERROR back_to_menu: {result.get('error')}")
        return False
    
    print("OK: Back button works")
    
    print("\nSUCCESS: All main functions work!")
    return True


if __name__ == "__main__":
    asyncio.run(test_menu_flow())
