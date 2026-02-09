"""User-facing failure UI helpers."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_kie_fail_ui(correlation_id: str, model_id: str, user_lang: str = "ru") -> tuple[str, InlineKeyboardMarkup]:
    """Build UX-friendly failure UI for KIE generation errors.
    
    Makes it clear that the error is on the AI provider side, not the bot.
    """
    short_id = correlation_id[-8:] if len(correlation_id) > 8 else correlation_id
    
    if user_lang == "ru":
        text = (
            "⚠️ <b>Генерация не удалась</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔧 <b>Причина:</b> Ошибка на стороне AI-провайдера\n\n"
            "❗️ <i>Это не ошибка бота — проблема у поставщика нейросети.</i>\n\n"
            "🔄 <b>Что делать:</b>\n"
            "• Нажмите «Повторить» через минуту\n"
            "• Или выберите другую модель\n\n"
            "💡 Ваш баланс <b>не списан</b>\n\n"
            f"ID: <code>{short_id}</code>"
        )
        retry_label = "🔁 Повторить"
        menu_label = "🏠 Главное меню"
        other_model_label = "🔄 Другая модель"
    else:
        text = (
            "⚠️ <b>Generation Failed</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔧 <b>Reason:</b> AI provider error\n\n"
            "❗️ <i>This is not a bot error — the issue is with the AI provider.</i>\n\n"
            "🔄 <b>What to do:</b>\n"
            "• Click «Retry» in a minute\n"
            "• Or choose a different model\n\n"
            "💡 Your balance was <b>not charged</b>\n\n"
            f"ID: <code>{short_id}</code>"
        )
        retry_label = "🔁 Retry"
        menu_label = "🏠 Main Menu"
        other_model_label = "🔄 Other Model"
    
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(retry_label, callback_data=f"retry_generate:{model_id}")],
            [InlineKeyboardButton(other_model_label, callback_data="show_all_models_list")],
            [InlineKeyboardButton(menu_label, callback_data="back_to_menu")],
        ]
    )
    return text, keyboard
