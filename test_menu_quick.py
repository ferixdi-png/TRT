#!/usr/bin/env python3
"""
Максимально простой тест для проверки меню.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from telegram.ext import CommandHandler, CallbackQueryHandler
from tests.ptb_harness import PTBHarness
from bot_kie import start, button_callback


async def test_menu():
    print("Starting menu test...")
    
    harness = PTBHarness()
    await harness.setup()
    
    # Добавляем обработчики правильно
    harness.application.add_handler(CommandHandler("start", start))
    harness.application.add_handler(CallbackQueryHandler(button_callback))
    
    user_id = 12345
    
    # Тестируем /start
    print("Testing /start...")
    result = await harness.process_command("/start", user_id=user_id)
    
    if result["success"]:
        print("SUCCESS: /start works")
        
        # Проверяем кнопки
        message = result.get("message")
        if message and message.reply_markup:
            keyboard = message.reply_markup.inline_keyboard
            print(f"Found {len(keyboard)} button rows")
            
            # Тестируем первую кнопку
            if keyboard and len(keyboard) > 0:
                first_button = keyboard[0][0]
                print(f"Testing first button: {first_button.text}")
                
                callback_result = await harness.process_callback(
                    first_button.callback_data, 
                    user_id=user_id
                )
                
                if callback_result["success"]:
                    print("SUCCESS: First button works")
                else:
                    print(f"ERROR: First button failed: {callback_result.get('error')}")
        else:
            print("ERROR: No keyboard in message")
    else:
        print(f"ERROR: /start failed: {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(test_menu())
