"""User-facing failure UI helpers."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_kie_fail_ui(correlation_id: str, model_id: str) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "❌ <b>Генерация не завершилась (KIE)</b>\n\n"
        f"correlation_id={correlation_id}\n"
        "Нажмите Повторить или вернитесь в меню."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Повторить", callback_data=f"retry_generate:{model_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")],
        ]
    )
    return text, keyboard
