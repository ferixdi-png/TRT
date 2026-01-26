"""Synchronous balance store wrappers for tests and integrations."""

from __future__ import annotations

import asyncio
import concurrent.futures

from app.services.user_service import get_user_balance, set_user_balance

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = _executor.submit(lambda: asyncio.run(coro))
    return future.result(timeout=5)


class BalanceStore:
    def get_balance(self, user_id: int) -> float:
        return float(_run_sync(get_user_balance(user_id)))

    def set_balance(self, user_id: int, amount: float) -> None:
        _run_sync(set_user_balance(user_id, float(amount)))


_balance_store = BalanceStore()


def get_balance_store() -> BalanceStore:
    return _balance_store
