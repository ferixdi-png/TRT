"""
Menu Builder - UI компоненты для построения меню.

Вынесено из bot_kie.py для декомпозиции.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from helpers import get_user_language_async


async def build_main_menu_keyboard(
    user_id: int,
    user_lang: str = 'ru',
    is_new: bool = False
) -> list[list[InlineKeyboardButton]]:
    """
    Строит главное меню клавиатуры.
    Обновлено согласно скриншоту идеального меню.
    """
    if user_lang == "ru":
        return [
            [InlineKeyboardButton("🆓 FAST TOOLS", callback_data="fast_tools")],
            [InlineKeyboardButton("🎨 Генерация визуала", callback_data="gen_type:text-to-image")],
            [InlineKeyboardButton("🧩 Ремикс изображения", callback_data="gen_type:image-to-image")],
            [InlineKeyboardButton("🎬 Видео по сценарию", callback_data="gen_type:text-to-video")],
            [InlineKeyboardButton("🪄 Анимировать изображение", callback_data="gen_type:image-to-video")],
            [InlineKeyboardButton("🧰 Спец-инструменты", callback_data="special_tools")],
            [InlineKeyboardButton("💳 Баланс / Доступ", callback_data="check_balance")],
            [InlineKeyboardButton("🤝 Партнёрка", callback_data="referral_info")],
        ]
    else:
        return [
            [InlineKeyboardButton("🆓 FAST TOOLS", callback_data="fast_tools")],
            [InlineKeyboardButton("🎨 Visual Generation", callback_data="gen_type:text-to-image")],
            [InlineKeyboardButton("🧩 Image Remix", callback_data="gen_type:image-to-image")],
            [InlineKeyboardButton("🎬 Video by Script", callback_data="gen_type:text-to-video")],
            [InlineKeyboardButton("🪄 Animate Image", callback_data="gen_type:image-to-video")],
            [InlineKeyboardButton("🧰 Special Tools", callback_data="special_tools")],
            [InlineKeyboardButton("💳 Balance / Access", callback_data="check_balance")],
            [InlineKeyboardButton("🤝 Referral", callback_data="referral_info")],
        ]


def build_minimal_menu_keyboard(user_lang: str) -> list[list[InlineKeyboardButton]]:
    """Строит минимальное меню для fallback."""
    if user_lang == "ru":
        return [
            [InlineKeyboardButton("📋 Модели", callback_data="show_models")],
            [InlineKeyboardButton("💳 Баланс", callback_data="check_balance")],
            [InlineKeyboardButton("🆘 Помощь", callback_data="help_menu")],
        ]
    else:
        return [
            [InlineKeyboardButton("📋 Models", callback_data="show_models")],
            [InlineKeyboardButton("💳 Balance", callback_data="check_balance")],
            [InlineKeyboardButton("🆘 Help", callback_data="help_menu")],
        ]


def build_back_to_menu_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    """Строит клавиатуру с кнопкой 'Назад в меню'."""
    if user_lang == "ru":
        button_text = "🔙 Назад в меню"
    else:
        button_text = "🔙 Back to menu"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data="back_to_menu")]
    ])


def build_confirmation_keyboard(
    user_lang: str,
    confirm_text: str = "✅ Подтвердить",
    cancel_text: str = "❌ Отмена"
) -> InlineKeyboardMarkup:
    """Строит клавиатуру для подтверждения."""
    if user_lang == "ru":
        confirm_btn = confirm_text
        cancel_btn = cancel_text
    else:
        confirm_btn = "✅ Confirm"
        cancel_btn = "❌ Cancel"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(confirm_btn, callback_data="confirm_generate"),
            InlineKeyboardButton(cancel_btn, callback_data="cancel_command")
        ]
    ])


def build_navigation_keyboard(
    user_lang: str,
    back_callback: str = "back_to_menu",
    additional_buttons: list[list[InlineKeyboardButton]] = None
) -> InlineKeyboardMarkup:
    """Строит навигационную клавиатуру."""
    keyboard = []
    
    # Добавляем дополнительные кнопки если есть
    if additional_buttons:
        keyboard.extend(additional_buttons)
    
    # Кнопка "Назад"
    if user_lang == "ru":
        back_text = "🔙 Назад"
    else:
        back_text = "🔙 Back"
    
    keyboard.append([InlineKeyboardButton(back_text, callback_data=back_callback)])
    
    return InlineKeyboardMarkup(keyboard)
