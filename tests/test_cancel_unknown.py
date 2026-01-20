"""Re-exported tests for cancel/unknown patterns."""

from tests.test_menu_anchor import (
    test_cancel_returns_to_main_menu,
    test_unknown_callback_returns_to_main_menu,
)

__all__ = [
    "test_cancel_returns_to_main_menu",
    "test_unknown_callback_returns_to_main_menu",
]
