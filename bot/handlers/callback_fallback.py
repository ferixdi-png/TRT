"""Catch-all fallback for callback queries to avoid 'infinite loading' buttons.

Must be included AFTER specific routers (flow, marketing, etc).
"""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
import logging

logger = logging.getLogger(__name__)
router = Router(name="callback_fallback")

@router.callback_query()
async def handle_unknown_callback(callback: CallbackQuery, state: FSMContext):
    """Catch-all fallback.

    Reality: users keep old messages with inline keyboards. After any UI update, those callbacks
    may no longer be routable. Instead of the annoying "press /start", we:
    - clear FSM state
    - show the current main menu
    """
    from bot.handlers.marketing import _build_main_menu_keyboard

    data = callback.data or ""
    uid = callback.from_user.id if callback.from_user else "-"
    logger.warning(f"E_CALLBACK unknown callback | uid={uid} data={data[:200]}")

    # Always stop the spinner
    try:
        await callback.answer("Меню обновилось — открываю актуальное 👇", show_alert=False)
    except Exception:
        pass

    # Reset stuck states (important for wizard)
    try:
        await state.clear()
    except Exception:
        pass

    msg = callback.message
    if not msg:
        return

    text = (
        "⚠️ Эта кнопка из старого меню (бот обновился).\n"
        "Вот актуальное меню — выбери раздел и продолжай." 
    )

    kb = _build_main_menu_keyboard()
    try:
        await msg.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await msg.answer(text, reply_markup=kb)
        except Exception:
            pass
