"""Local JSON file storage (fallback)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class FileStorage:
    def __init__(self) -> None:
        prefix = os.getenv("STORAGE_PREFIX", "storage")
        data_dir = Path(__file__).resolve().parents[2] / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._path = data_dir / f"{prefix}_users.json"

    async def _load(self) -> dict:
        if not self._path.exists():
            return {"users": {}}
        data = await asyncio.to_thread(self._path.read_text)
        return json.loads(data) if data else {"users": {}}

    async def _save(self, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        await asyncio.to_thread(self._path.write_text, text)

    async def get_user(self, user_id: int) -> dict:
        payload = await self._load()
        return payload.setdefault("users", {}).setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})

    async def get_user_balance(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return int(user.get("balance", 0))

    async def set_user_balance(self, user_id: int, balance: int) -> None:
        payload = await self._load()
        users = payload.setdefault("users", {})
        record = users.setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})
        record["balance"] = int(balance)
        await self._save(payload)

    async def add_purchase(self, user_id: int, item: dict) -> None:
        payload = await self._load()
        users = payload.setdefault("users", {})
        record = users.setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})
        record.setdefault("purchases", []).append(item)
        await self._save(payload)

    async def add_history(self, user_id: int, entry: dict) -> None:
        payload = await self._load()
        users = payload.setdefault("users", {})
        record = users.setdefault(str(user_id), {"balance": 0, "purchases": [], "history": []})
        record.setdefault("history", []).append(entry)
        await self._save(payload)


async def init_file_storage() -> FileStorage:
    storage = FileStorage()
    await storage._load()
    logger.info("[STORAGE] FileStorage ready path=%s", storage._path)
    return storage
