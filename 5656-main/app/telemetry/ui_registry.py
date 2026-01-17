"""UI registry enums."""
from __future__ import annotations

from enum import Enum


class ScreenId(str, Enum):
    MAIN_MENU = "main_menu"
    QUICK_MENU = "quick_menu"
    CATALOG = "catalog"


class ButtonId(str, Enum):
    QUICK_MENU = "quick_menu"
    MAIN_MENU = "main_menu"
    CATALOG = "catalog"
    BALANCE = "balance"
