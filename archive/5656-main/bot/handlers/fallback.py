"""Fallback handlers for unknown callbacks/messages."""
from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.handlers.flow import build_main_menu

logger = logging.getLogger(__name__)

router = Router(name="fallback")


@router.callback_query()
async def fallback_callback(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return
    text, markup = build_main_menu()
    logger.info("[FALLBACK] Unknown callback data=%s", callback.data)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.message()
async def fallback_message(message: Message):
    text, markup = build_main_menu()
    logger.info("[FALLBACK] Unknown message received")
    await message.answer(text, reply_markup=markup)
