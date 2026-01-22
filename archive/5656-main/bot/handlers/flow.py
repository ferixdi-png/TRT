"""Main menu flow handlers (no language picker)."""
from __future__ import annotations

import logging
import os

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.telemetry.telemetry_helpers import log_ui_render
from app.telemetry.ui_registry import ScreenId
from bot.menu import build_main_menu_data, build_catalog_text

logger = logging.getLogger(__name__)

router = Router(name="flow")


def build_main_menu() -> tuple[str, InlineKeyboardMarkup]:
    text, buttons = build_main_menu_data()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=data)] for label, data in buttons]
    )
    return text, markup


@router.message(CommandStart())
async def start(message: Message):
    if not message.from_user:
        logger.error("[START] message.from_user is None")
        return
    text, markup = build_main_menu()
    log_ui_render("start", message.from_user.id, message.chat.id, ScreenId.MAIN_MENU)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    if not callback.message or not callback.from_user:
        await callback.answer("Ошибка", show_alert=True)
        return
    text, markup = build_main_menu()
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data == "catalog")
async def catalog(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return
    text = build_catalog_text()
    if text == "Каталог пока недоступен.":
        await callback.message.edit_text("Каталог пока недоступен.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]]
        ))
        return
    buttons = [[InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    if not callback.message:
        await callback.answer("Ошибка", show_alert=True)
        return
    support_text = os.getenv("SUPPORT_TEXT", "Если у вас возникли вопросы, напишите администратору")
    support_contact = os.getenv("SUPPORT_TELEGRAM", "")
    body = f"🆘 <b>Поддержка</b>\n\n{support_text}"
    if support_contact:
        body += f"\n\nКонтакт: {support_contact}"
    await callback.message.edit_text(body, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]]
    ))
    await callback.answer()
