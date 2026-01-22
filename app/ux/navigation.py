"""Navigation helpers for UX flows."""
from __future__ import annotations

from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_back_to_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка 🏠 Главное меню"""
    if lang == "en":
        label = "🏠 Main Menu"
    else:
        label = "🏠 Главное меню"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="back_to_menu")]])


def build_back_to_models_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка 🔙 Назад к моделям"""
    if lang == "en":
        label = "🔙 Back to models"
    else:
        label = "🔙 Назад к моделям"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="show_models")]])


def build_cancel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка ❌ Отмена"""
    if lang == "en":
        label = "❌ Cancel"
    else:
        label = "❌ Отмена"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="cancel")]])


def build_back_and_home_keyboard(lang: str = "ru", back_callback: str = "show_models") -> InlineKeyboardMarkup:
    """Две кнопки: 🔙 Назад | 🏠 Главное меню"""
    if lang == "en":
        back_label = "🔙 Back"
        home_label = "🏠 Main Menu"
    else:
        back_label = "🔙 Назад"
        home_label = "🏠 Главное меню"
    
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(back_label, callback_data=back_callback),
        InlineKeyboardButton(home_label, callback_data="back_to_menu")
    ]])


def build_navigation_row(buttons: List[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    """Создать клавиатуру из списка кнопок (одна строка)"""
    return InlineKeyboardMarkup([buttons])


def add_navigation_buttons(
    keyboard: List[List[InlineKeyboardButton]], 
    lang: str = "ru",
    back_callback: Optional[str] = None,
    show_home: bool = True,
    show_cancel: bool = False
) -> List[List[InlineKeyboardButton]]:
    """
    Добавляет навигационные кнопки к существующей клавиатуре
    
    Args:
        keyboard: Существующая клавиатура (список строк кнопок)
        lang: Язык интерфейса
        back_callback: Callback для кнопки "Назад" (если None - не добавляется)
        show_home: Показывать кнопку "Главное меню"
        show_cancel: Показывать кнопку "Отмена" вместо Home/Back
    
    Returns:
        Клавиатура с добавленными навигационными кнопками
    """
    nav_row = []
    
    if show_cancel:
        # Только кнопка Отмена
        cancel_label = "❌ Cancel" if lang == "en" else "❌ Отмена"
        nav_row.append(InlineKeyboardButton(cancel_label, callback_data="cancel"))
    else:
        # Назад + Домой
        if back_callback:
            back_label = "🔙 Back" if lang == "en" else "🔙 Назад"
            nav_row.append(InlineKeyboardButton(back_label, callback_data=back_callback))
        
        if show_home:
            home_label = "🏠 Main Menu" if lang == "en" else "🏠 Главное меню"
            nav_row.append(InlineKeyboardButton(home_label, callback_data="back_to_menu"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    return keyboard


def get_back_button(lang: str = "ru", callback: str = "show_models") -> InlineKeyboardButton:
    """Получить кнопку 🔙 Назад"""
    label = "🔙 Back" if lang == "en" else "🔙 Назад"
    return InlineKeyboardButton(label, callback_data=callback)


def get_home_button(lang: str = "ru") -> InlineKeyboardButton:
    """Получить кнопку 🏠 Главное меню"""
    label = "🏠 Main Menu" if lang == "en" else "🏠 Главное меню"
    return InlineKeyboardButton(label, callback_data="back_to_menu")


def get_cancel_button(lang: str = "ru") -> InlineKeyboardButton:
    """Получить кнопку ❌ Отмена"""
    label = "❌ Cancel" if lang == "en" else "❌ Отмена"
    return InlineKeyboardButton(label, callback_data="cancel")
