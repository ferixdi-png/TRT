import asyncio

import pytest

from app.services import user_service


class DummyStorage:
    def __init__(self):
        self.balance = 0.0

    async def add_user_balance(self, _user_id: int, amount: float) -> float:
        current = self.balance
        await asyncio.sleep(0)
        self.balance = current + amount
        return self.balance

    async def subtract_user_balance(self, _user_id: int, amount: float) -> bool:
        current = self.balance
        await asyncio.sleep(0)
        if current < amount:
            return False
        self.balance = current - amount
        return True

    async def set_user_balance(self, _user_id: int, amount: float) -> None:
        await asyncio.sleep(0)
        self.balance = amount


@pytest.mark.asyncio
async def test_concurrent_balance_updates_serialized(monkeypatch):
    storage = DummyStorage()
    monkeypatch.setattr(user_service, "get_storage", lambda: storage)

    await asyncio.gather(
        user_service.add_user_balance(1, 5),
        user_service.add_user_balance(1, 7),
        user_service.add_user_balance(1, 3),
    )

    assert storage.balance == 15.0
