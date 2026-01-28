"""
Bot UI components.

Модули для построения пользовательского интерфейса.
"""

from .menu_builder import (
    build_main_menu_keyboard,
    build_minimal_menu_keyboard,
    build_back_to_menu_keyboard,
    build_confirmation_keyboard,
    build_navigation_keyboard
)

__all__ = [
    'build_main_menu_keyboard',
    'build_minimal_menu_keyboard', 
    'build_back_to_menu_keyboard',
    'build_confirmation_keyboard',
    'build_navigation_keyboard'
]
