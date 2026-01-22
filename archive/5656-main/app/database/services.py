"""Database service stubs."""
from __future__ import annotations


class DatabaseService:
    def __init__(self, _database_url: str):
        self._pool = None


class UIStateService:
    def __init__(self, _db_service: DatabaseService):
        self._db_service = _db_service

    async def cleanup_expired(self) -> None:
        return None
