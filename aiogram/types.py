"""Minimal types stubs for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class User:
    id: int
    is_bot: bool
    first_name: str


@dataclass
class Chat:
    id: int
    type: str


@dataclass
class Message:
    message_id: int | None = None
    from_user: Optional[User] = None
    chat: Optional[Chat] = None
    text: Optional[str] = None


@dataclass
class CallbackQuery:
    id: str | None = None
    from_user: Optional[User] = None
    message: Optional[Message] = None
    data: Optional[str] = None


@dataclass
class ErrorEvent:
    exception: Exception | None = None
    update: Optional[object] = None


@dataclass
class InlineKeyboardButton:
    text: str
    callback_data: str


@dataclass
class InlineKeyboardMarkup:
    inline_keyboard: List[List[InlineKeyboardButton]] = field(default_factory=list)


@dataclass
class InputMediaPhoto:
    media: str
    caption: str | None = None
