"""History handlers."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.storage import get_storage

logger = logging.getLogger(__name__)

router = Router(name="history")


@router.callback_query(F.data == "history")
async def show_history(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return
    storage = get_storage()
    history = []
    try:
        if hasattr(storage, "get_user"):
            record = await storage.get_user(callback.from_user.id)
            history = record.get("history", [])
    except Exception as exc:
        logger.warning("[HISTORY] Failed to fetch history: %s", exc)
    lines = ["🧾 <b>История</b>"]
    if not history:
        lines.append("\nИстория пока пуста.")
    else:
        lines.append("")
        for item in history[-10:]:
            lines.append(f"• {item}")
    buttons = [[InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]]
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()
