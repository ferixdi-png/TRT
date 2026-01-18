"""Navigation helpers for UX flows."""
from __future__ import annotations

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_back_to_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        label = "🏠 Main Menu"
    else:
        label = "🏠 Главное меню"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="back_to_menu")]])


def build_back_to_models_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    if lang == "en":
        label = "🔙 Back to models"
    else:
        label = "🔙 Назад к моделям"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="show_models")]])


def build_navigation_row(buttons: List[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([buttons])
