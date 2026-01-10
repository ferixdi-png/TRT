"""Minimal aiogram stubs for tests."""

from .router import Router
from .filters import Command
from .types import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

class _FilterSentinel:
    def __getattr__(self, _name):
        return self

    def __eq__(self, _other):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def in_(self, _values):
        return self

F = _FilterSentinel()

__all__ = [
    "F",
    "Router",
    "Command",
    "CallbackQuery",
    "Chat",
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "Message",
    "User",
]
