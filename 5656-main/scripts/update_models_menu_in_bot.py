#!/usr/bin/env python3
"""
Скрипт для обновления обработчиков моделей в bot_kie.py.
Добавляет использование нового каталога.
"""

import re
from pathlib import Path

root_dir = Path(__file__).parent.parent
bot_kie_file = root_dir / "bot_kie.py"

def update_show_all_models_list():
    """Обновляет обработчик show_all_models_list."""
    with open(bot_kie_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерн для поиска обработчика
    pattern = r'(        if data == "show_all_models_list":.*?)(            try:\s+await query\.edit_message_text\([^)]+\))'
    
    replacement = r'''\1            # Используем новый каталог
            try:
                from app.helpers.models_menu_handlers import handle_show_all_models_list
                user_lang = get_user_language(user_id)
                await handle_show_all_models_list(query, user_id, user_lang)
                return SELECTING_MODEL
            except Exception as e:
                logger.error(f"Error in handle_show_all_models_list: {e}", exc_info=True)
                user_lang = get_user_language(user_id)
                if user_lang == 'ru':
                    error_msg = "❌ Ошибка при загрузке моделей. Попробуйте позже."
                else:
                    error_msg = "❌ Error loading models. Please try later."
                await query.answer(error_msg, show_alert=True)
                return SELECTING_MODEL
            
            # Старый код (закомментирован для безопасности)
            # try:
            #     await query.edit_message_text(
            #         models_text,'''
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open(bot_kie_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Updated show_all_models_list handler")


def update_model_callback():
    """Обновляет обработчики model: callback."""
    with open(bot_kie_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерн для поиска обработчика model:
    pattern = r'(        if data\.startswith\("model:"\):.*?)(            try:\s+await query\.edit_message_text\([^)]+\))'
    
    replacement = r'''\1            # Используем новый каталог
            user_lang = get_user_language(user_id)
            
            try:
                from app.helpers.models_menu_handlers import handle_model_callback
                success = await handle_model_callback(query, user_id, user_lang, data)
                
                if success:
                    return SELECTING_MODEL
                else:
                    return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error in handle_model_callback: {e}", exc_info=True)
                if user_lang == 'ru':
                    await query.answer("❌ Ошибка при загрузке модели", show_alert=True)
                else:
                    await query.answer("❌ Error loading model", show_alert=True)
                return ConversationHandler.END
            
            # Старый код (закомментирован для безопасности)
            # try:
            #     await query.edit_message_text('''
    
    # Заменяем все вхождения
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    with open(bot_kie_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ Updated model: callback handlers")


if __name__ == "__main__":
    print("Updating bot_kie.py handlers...")
    update_show_all_models_list()
    update_model_callback()
    print("✅ All handlers updated!")

