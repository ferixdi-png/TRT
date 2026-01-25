"""
User service - чистые функции для работы с пользователями
БЕЗ зависимостей от bot_kie.py (устраняет circular imports)
"""

import logging
import asyncio
from typing import Optional, Dict

import asyncpg

from app.utils.retry import retry_with_backoff
from app.storage import get_storage

logger = logging.getLogger(__name__)

# Глобальный кэш для admin проверок (чтобы не обращаться к storage каждый раз)
_admin_cache: dict[int, bool] = {}
_user_locks: Dict[int, asyncio.Lock] = {}
_TRANSIENT_EXCEPTIONS = (
    asyncpg.exceptions.DeadlockDetectedError,
    asyncpg.exceptions.SerializationError,
    asyncpg.exceptions.CannotConnectNowError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
    ConnectionResetError,
    TimeoutError,
)


def _get_user_lock(user_id: int) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[user_id] = lock
    return lock


def _get_storage():
    """Получить storage instance"""
    return get_storage()


async def _call_with_retry(func, *args):
    return await retry_with_backoff(
        func,
        *args,
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        exceptions=_TRANSIENT_EXCEPTIONS,
    )


async def get_user_balance(user_id: int) -> float:
    """Получить баланс пользователя"""
    storage = _get_storage()
    return await _call_with_retry(storage.get_user_balance, user_id)


async def set_user_balance(user_id: int, amount: float) -> None:
    """Установить баланс пользователя"""
    storage = _get_storage()
    async with _get_user_lock(user_id):
        await _call_with_retry(storage.set_user_balance, user_id, amount)


async def add_user_balance(user_id: int, amount: float) -> float:
    """Добавить к балансу пользователя"""
    storage = _get_storage()
    async with _get_user_lock(user_id):
        return await _call_with_retry(storage.add_user_balance, user_id, amount)


async def subtract_user_balance(user_id: int, amount: float) -> bool:
    """Вычесть из баланса пользователя"""
    storage = _get_storage()
    async with _get_user_lock(user_id):
        return await _call_with_retry(storage.subtract_user_balance, user_id, amount)


async def get_user_language(user_id: int) -> str:
    """Получить язык пользователя"""
    storage = _get_storage()
    return await storage.get_user_language(user_id)


async def set_user_language(user_id: int, language: str) -> None:
    """Установить язык пользователя"""
    storage = _get_storage()
    await storage.set_user_language(user_id, language)


async def has_claimed_gift(user_id: int) -> bool:
    """Проверить получение подарка"""
    storage = _get_storage()
    return await storage.has_claimed_gift(user_id)


async def set_gift_claimed(user_id: int) -> None:
    """Отметить получение подарка"""
    storage = _get_storage()
    await storage.set_gift_claimed(user_id)


async def get_user_free_generations_remaining(user_id: int) -> int:
    """Получить оставшиеся бесплатные генерации"""
    from app.services.free_tools_service import get_free_generation_status

    status = await get_free_generation_status(user_id)
    return int(status.get("total_remaining", 0))


def get_is_admin(user_id: int) -> bool:
    """Проверить является ли пользователь админом (синхронно)"""
    from app.admin.auth import is_admin

    return is_admin(user_id)


async def get_admin_limit(user_id: int) -> float:
    """Получить лимит админа"""
    storage = _get_storage()
    return await storage.get_admin_limit(user_id)


async def get_admin_spent(user_id: int) -> float:
    """Получить потраченную сумму админа"""
    storage = _get_storage()
    return await storage.get_admin_spent(user_id)


async def get_admin_remaining(user_id: int) -> float:
    """Получить оставшийся лимит админа"""
    storage = _get_storage()
    return await storage.get_admin_remaining(user_id)


# Синхронные обертки для обратной совместимости (используют asyncio.run внутри)
# ВНИМАНИЕ: Эти функции блокируют event loop! Используйте async версии в async контексте
def get_user_balance_sync(user_id: int) -> float:
    """Синхронная обертка для get_user_balance (для обратной совместимости)"""
    import asyncio
    import traceback

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        stack = "".join(traceback.format_stack(limit=12))
        logger.error(
            "SYNC_WRAPPER_CALLED_IN_ASYNC wrapper=get_user_balance_sync stack=%s",
            stack,
        )
        raise RuntimeError("get_user_balance_sync called inside running event loop")

    return asyncio.run(get_user_balance(user_id))


def get_user_language_sync(user_id: int) -> str:
    """Синхронная обертка для get_user_language (для обратной совместимости)"""
    import asyncio
    import traceback

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        stack = "".join(traceback.format_stack(limit=12))
        logger.error(
            "SYNC_WRAPPER_CALLED_IN_ASYNC wrapper=get_user_language_sync stack=%s",
            stack,
        )
        raise RuntimeError("get_user_language_sync called inside running event loop")

    return asyncio.run(get_user_language(user_id))
