"""
User state - синхронные и async функции для работы с пользователями
БЕЗ зависимостей от bot_kie.py (устраняет circular imports)

Использует app/services/user_service для async операций
и предоставляет синхронные обертки для обратной совместимости.
"""

import logging
import asyncio
from typing import Optional
from app.services.user_service import (
    get_user_balance as get_user_balance_async_service,
    get_user_language as get_user_language_async_service,
    get_user_free_generations_remaining as get_user_free_generations_remaining_service,
    has_claimed_gift as has_claimed_gift_service,
    get_admin_limit as get_admin_limit_service,
    get_admin_spent as get_admin_spent_service,
    get_admin_remaining as get_admin_remaining_service,
    get_is_admin as get_is_admin_service,
)

logger = logging.getLogger(__name__)


def _log_sync_wrapper_call(wrapper_name: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if loop.is_running():
        import traceback

        stack = "".join(traceback.format_stack(limit=12))
        logger.error(
            "SYNC_WRAPPER_CALLED_IN_ASYNC wrapper=%s stack=%s",
            wrapper_name,
            stack,
        )
        raise RuntimeError(f"{wrapper_name} called inside running event loop")


def _run_async_safe(coro, wrapper_name: str):
    """
    Безопасный запуск async функции в синхронном контексте.
    """
    _log_sync_wrapper_call(wrapper_name)
    try:
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"Error running async function: {e}", exc_info=True)
        raise


# ==================== Async версии (рекомендуется для async контекста) ====================

async def get_user_balance_async(user_id: int) -> float:
    """Получить баланс пользователя (async)"""
    return await get_user_balance_async_service(user_id)


async def get_user_language_async(user_id: int) -> str:
    """Получить язык пользователя (async)"""
    return await get_user_language_async_service(user_id)


# get_is_admin уже синхронный
def get_is_admin(user_id: int) -> bool:
    """Проверить является ли пользователь админом (синхронно)"""
    return get_is_admin_service(user_id)


# ==================== Синхронные версии (для обратной совместимости) ====================

def get_user_balance(user_id: int) -> float:
    """
    Получить баланс пользователя (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте get_user_balance_async() в async контексте.
    """
    return _run_async_safe(get_user_balance_async_service(user_id), "get_user_balance")


def get_user_language(user_id: int) -> str:
    """
    Получить язык пользователя (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте get_user_language_async() в async контексте.
    """
    return _run_async_safe(get_user_language_async_service(user_id), "get_user_language")


def get_user_free_generations_remaining(user_id: int) -> int:
    """
    Получить оставшиеся бесплатные генерации (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте async версию в async контексте.
    """
    return _run_async_safe(
        get_user_free_generations_remaining_service(user_id),
        "get_user_free_generations_remaining",
    )


def has_claimed_gift(user_id: int) -> bool:
    """
    Проверить получение подарка (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте async версию в async контексте.
    """
    return _run_async_safe(has_claimed_gift_service(user_id), "has_claimed_gift")


def get_admin_limit(user_id: int) -> float:
    """
    Получить лимит админа (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте async версию в async контексте.
    """
    return _run_async_safe(get_admin_limit_service(user_id), "get_admin_limit")


def get_admin_spent(user_id: int) -> float:
    """
    Получить потраченную сумму админа (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте async версию в async контексте.
    """
    return _run_async_safe(get_admin_spent_service(user_id), "get_admin_spent")


def get_admin_remaining(user_id: int) -> float:
    """
    Получить оставшийся лимит админа (синхронная обертка).
    
    ВНИМАНИЕ: Эта функция блокирует event loop!
    Используйте async версию в async контексте.
    """
    return _run_async_safe(get_admin_remaining_service(user_id), "get_admin_remaining")
