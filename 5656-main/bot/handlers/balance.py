"""Balance handlers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.storage import get_storage

logger = logging.getLogger(__name__)

router = Router(name="balance")


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return
    storage = get_storage()
    balance = 0
    try:
        if hasattr(storage, "get_user_balance"):
            balance = await storage.get_user_balance(callback.from_user.id)
    except Exception as exc:
        logger.warning("[BALANCE] Failed to fetch balance: %s", exc)
    body = (
        "💰 <b>Ваш баланс</b>\n\n"
        f"Текущий баланс: <b>{balance}</b>"
    )
    buttons = [[InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]]
    await callback.message.edit_text(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()
