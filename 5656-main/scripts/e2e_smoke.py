"""E2E smoke simulation for /start and menu callbacks."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bot.menu import build_catalog_text, build_main_menu_data
from app.storage import get_storage


@dataclass
class DummyUser:
    id: int


@dataclass
class DummyChat:
    id: int


class DummyMessage:
    def __init__(self, user_id: int, chat_id: int) -> None:
        self.from_user = DummyUser(user_id)
        self.chat = DummyChat(chat_id)
        self.responses = []

    async def answer(self, text: str, reply_markup=None):
        self.responses.append(("answer", text))

    async def edit_text(self, text: str, reply_markup=None):
        self.responses.append(("edit_text", text))


class DummyCallback:
    def __init__(self, user_id: int, chat_id: int, data: str) -> None:
        self.from_user = DummyUser(user_id)
        self.message = DummyMessage(user_id, chat_id)
        self.data = data

    async def answer(self, *args, **kwargs):
        return None


async def run() -> None:
    user_id = 123456
    _ = DummyMessage(user_id, 123456)

    menu_text, menu_buttons = build_main_menu_data()
    print("/start menu:", menu_text, menu_buttons)

    catalog_text = build_catalog_text()
    print("catalog:", catalog_text.splitlines()[0] if catalog_text else "empty")

    storage = get_storage()
    if hasattr(storage, "set_user_balance"):
        await storage.set_user_balance(user_id, 42)
    if hasattr(storage, "add_history"):
        await storage.add_history(user_id, {"event": "smoke", "value": 1})
    if hasattr(storage, "get_user_balance"):
        balance = await storage.get_user_balance(user_id)
        print(f"Storage balance for {user_id}: {balance}")


if __name__ == "__main__":
    asyncio.run(run())
