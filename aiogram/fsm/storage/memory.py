"""Minimal in-memory storage stub."""

from __future__ import annotations

from typing import Any, Dict


class MemoryStorage:
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._state: Dict[str, Any] = {}

    async def get_data(self, key: str) -> Dict[str, Any]:
        return dict(self._data.get(key, {}))

    async def set_data(self, key: str, data: Dict[str, Any]) -> None:
        self._data[key] = dict(data)

    async def set_state(self, key: str, state: Any) -> None:
        self._state[key] = state

    async def clear(self, key: str) -> None:
        self._data.pop(key, None)
        self._state.pop(key, None)
