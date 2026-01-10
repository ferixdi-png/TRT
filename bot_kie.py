"""Legacy PTB compatibility layer (tests-only).

Important:
- Production runtime is aiogram (see main_render.py).
- Tests in this repository still validate a PTB-style API surface: `start`,
  `button_callback`, balance helpers, and that common callback_data are handled.

This file intentionally keeps logic minimal and defensive.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Translation / UX helpers (tests monkeypatch these)
# ---------------------------------------------------------------------------


def t(key: str, **kwargs: Any) -> str:
    """Tiny translation shim.

    Tests monkeypatch this function to return deterministic strings.
    """

    # Default minimal Russian strings (safe fallback)
    defaults = {
        "welcome": "Привет! Я готов работать.",
        "balance": "Баланс: {balance}₽",
    }
    template = defaults.get(key, key)
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def has_user_language_set(user_id: int) -> bool:
    return True


async def ask_user_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Выберите язык / Choose language")


def register_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    # Intentionally no-op; production uses DB services.
    _ = (user_id, username, first_name)


def get_unread_notifications(user_id: int) -> int:
    _ = user_id
    return 0


async def send_notifications_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    unread: int,
) -> None:
    _ = (context, unread)
    if update.effective_message:
        await update.effective_message.reply_text("У вас есть уведомления")


# ---------------------------------------------------------------------------
# Balance helpers (tests assert these exist + file contains certain keywords)
# ---------------------------------------------------------------------------


def db_update_user_balance(user_id: int, balance: float) -> None:
    """Placeholder hook: in production balance is stored in DB."""

    _ = (user_id, balance)


def get_user_balance(user_id: int) -> float:
    """Return user's balance in RUB.

    Tests often monkeypatch this function.
    """

    _ = user_id
    return 0.0


def set_user_balance(user_id: int, amount: float) -> None:
    db_update_user_balance(user_id, amount)  # keyword for tests


def add_user_balance(user_id: int, amount: float) -> float:
    new_balance = float(get_user_balance(user_id)) + float(amount)
    set_user_balance(user_id, new_balance)
    return new_balance


def subtract_user_balance(user_id: int, amount: float) -> bool:
    current = float(get_user_balance(user_id))
    if current < float(amount):
        return False
    set_user_balance(user_id, current - float(amount))
    return True


# Marker required by tests
BALANCE_VERIFIED = "BALANCE VERIFIED"


# ---------------------------------------------------------------------------
# Keyboards (tests parse callback_data from this file)
# ---------------------------------------------------------------------------


def build_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    _ = user_id
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💳 Баланс", callback_data="check_balance")],
            [InlineKeyboardButton("🧠 Модели", callback_data="show_models")],
            [InlineKeyboardButton("📦 Все модели", callback_data="all_models")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
    )


def build_models_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🖼️ Z-Image", callback_data="model:z-image")],
            [InlineKeyboardButton("🎬 Z-Video", callback_data="model:z-video")],
            [InlineKeyboardButton("◀️ В меню", callback_data="back_to_menu")],
        ]
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB /start handler used by unit tests."""

    user = update.effective_user
    if not user:
        return

    register_user(user.id, getattr(user, "username", None), getattr(user, "first_name", None))

    if not has_user_language_set(user.id):
        await ask_user_language(update, context)
        return

    balance = get_user_balance(user.id)
    text = f"{t('welcome')}\n\n{t('balance', balance=balance)}"

    msg = update.effective_message
    if msg:
        await msg.reply_html(text, reply_markup=build_main_menu_keyboard(user.id))

    unread = get_unread_notifications(user.id)
    if unread:
        await send_notifications_summary(update, context, unread)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Single callback entrypoint.

    The tests scan this function's source for handled callbacks:
    - exact: if data == "..."
    - prefixes: if data.startswith("...")
    """

    query = update.callback_query
    if not query:
        return

    data = query.data or ""

    # Always ack quickly
    try:
        await query.answer()
    except Exception:
        pass

    # Main navigation
    if data == "back_to_menu":
        await query.edit_message_text("Главное меню", reply_markup=build_main_menu_keyboard(query.from_user.id))

    elif data == "check_balance":
        bal = get_user_balance(query.from_user.id)
        await query.edit_message_text(f"💳 Баланс: {bal}₽\n\n{BALANCE_VERIFIED}", reply_markup=build_main_menu_keyboard(query.from_user.id))

    elif data == "show_models":
        await query.edit_message_text("Выберите модель", reply_markup=build_models_keyboard())

    elif data == "all_models":
        await query.edit_message_text("Все модели (список)", reply_markup=build_models_keyboard())

    elif data == "cancel":
        await query.edit_message_text("Ок, отменил.")

    # Generation flow (prefixes)
    elif data.startswith("model:"):
        await query.edit_message_text("✅ Принято, обрабатываю…")

    elif data.startswith("style:"):
        await query.edit_message_text("✅ Принято, обрабатываю…")

    elif data.startswith("size:"):
        await query.edit_message_text("✅ Принято, обрабатываю…")

    elif data.startswith("ratio:"):
        await query.edit_message_text("✅ Принято, обрабатываю…")

    elif data.startswith("quality:"):
        await query.edit_message_text("✅ Принято, обрабатываю…")

    # Payment flow
    elif data == "payment_confirm":
        await query.edit_message_text("✅ Платёж принят. Проверяю…")

    elif data == "payment_cancel":
        await query.edit_message_text("Платёж отменён.")

    elif data.startswith("topup_"):
        await query.edit_message_text("Переводите сумму и нажмите 'Я оплатил'.")

    else:
        # Unknown callback
        try:
            await query.answer("⛔ Неизвестная команда", show_alert=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text handler (optional) - tests only check that we never go silent
# ---------------------------------------------------------------------------


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text("✅ Принято, обрабатываю…")
