"""Minimal FSM context stub."""

from __future__ import annotations

from typing import Any, Dict


class FSMContext:
    def __init__(self, storage, key: str):
        self.storage = storage
        self.key = key

    async def update_data(self, **kwargs) -> None:
        data = await self.storage.get_data(self.key)
        data.update(kwargs)
        await self.storage.set_data(self.key, data)

    async def get_data(self) -> Dict[str, Any]:
        return await self.storage.get_data(self.key)

    async def set_state(self, state) -> None:
        await self.storage.set_state(self.key, state)

    async def clear(self) -> None:
        await self.storage.clear(self.key)
