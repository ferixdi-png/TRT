"""Navigation / main menu render.

This router must never produce dead buttons.
It should only emit callback_data that has exactly one handler.
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.ui.catalog import get_counts
from app.pricing.free_models import get_free_models

logger = logging.getLogger(__name__)

router = Router(name="navigation")


def _build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build main menu keyboard using only live callbacks."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏆 Популярное", callback_data="menu:popular"),
                InlineKeyboardButton(text="🧩 Все форматы", callback_data="menu:formats"),
            ],
            [
                InlineKeyboardButton(text="🎁 Бесплатные", callback_data="menu:free"),
                InlineKeyboardButton(text="🔎 Поиск", callback_data="menu:search"),
            ],
            [
                InlineKeyboardButton(text="📜 История", callback_data="menu:history"),
                InlineKeyboardButton(text="⭐ Избранные", callback_data="menu:favorites"),
            ],
            [
                InlineKeyboardButton(text="💳 Баланс", callback_data="menu:balance"),
                InlineKeyboardButton(text="🔁 Повторить последнюю", callback_data="quick:repeat_last"),
            ],
            [
                InlineKeyboardButton(text="⚡ Быстрые действия", callback_data="quick:menu"),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
            ],
        ]
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    """Legacy alias: main_menu -> menu:main.

    NOTE: aiogram v3 CallbackQuery is a frozen pydantic model; never mutate callback.data.
    """
    return await cb_menu_main(callback, state)


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext):
    """Show main menu and clear any ongoing FSM state."""
    await callback.answer()
    await state.clear()

    try:
        counts = get_counts()
        total = sum(counts.values())
        free_count = len(get_free_models())

        text = (
            f"🏠 <b>Главное меню</b>\n\n"
            f"🚀 {total} нейросетей • 🎁 {free_count} бесплатно"
        )

        await callback.message.edit_text(
            text,
            reply_markup=_build_main_menu_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to render main menu: %s", e, exc_info=True)
        await callback.message.answer("🏠 /start — вернуться в меню")

