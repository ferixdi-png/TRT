"""
Timeout protection utilities for external API calls.

PR-5: Request Timeout Coverage (MEDIUM priority)

Provides graceful timeout handling for Telegram API and other external calls
to prevent indefinite hangs.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional, TypeVar

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def with_timeout(
    coro: Callable[..., Any],
    timeout_seconds: float,
    *args: Any,
    operation_name: str = "operation",
    fallback: Optional[T] = None,
    **kwargs: Any,
) -> Optional[T]:
    """
    Execute coroutine with timeout protection.
    
    Args:
        coro: Async callable to execute
        timeout_seconds: Maximum time to wait
        *args: Positional arguments for coro
        operation_name: Human-readable name for logging
        fallback: Value to return on timeout (if None, re-raise TimeoutError)
        **kwargs: Keyword arguments for coro
        
    Returns:
        Result from coro or fallback value
        
    Raises:
        asyncio.TimeoutError: If timeout exceeded and fallback is None
    """
    try:
        result = await asyncio.wait_for(
            coro(*args, **kwargs),
            timeout=timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(
            "TIMEOUT operation=%s timeout=%.1fs fallback=%s",
            operation_name,
            timeout_seconds,
            "provided" if fallback is not None else "none",
            exc_info=True,
        )
        if fallback is not None:
            return fallback
        raise


async def send_message_safe(
    context_or_bot: Any,
    chat_id: int,
    text: str,
    timeout: float = 30.0,
    **kwargs: Any,
) -> Optional[Any]:
    """
    Send Telegram message with timeout protection.
    
    Args:
        context_or_bot: Telegram Bot or Application context
        chat_id: Chat ID to send to
        text: Message text
        timeout: Timeout in seconds
        **kwargs: Additional arguments for send_message
        
    Returns:
        Message object or None on timeout
    """
    try:
        # Detect if context or bot
        if hasattr(context_or_bot, "bot"):
            bot = context_or_bot.bot
        else:
            bot = context_or_bot
        
        return await with_timeout(
            bot.send_message,
            timeout,
            chat_id=chat_id,
            text=text,
            operation_name=f"send_message(chat_id={chat_id})",
            **kwargs,
        )
    except asyncio.TimeoutError:
        logger.error(
            "SEND_MESSAGE_TIMEOUT chat_id=%s text_length=%s timeout=%.1fs",
            chat_id,
            len(text),
            timeout,
        )
        return None
    except Exception as exc:
        logger.error(
            "SEND_MESSAGE_FAILED chat_id=%s error=%s",
            chat_id,
            exc,
            exc_info=True,
        )
        return None


async def edit_message_safe(
    context_or_bot: Any,
    chat_id: int,
    message_id: int,
    text: str,
    timeout: float = 30.0,
    **kwargs: Any,
) -> Optional[Any]:
    """
    Edit Telegram message with timeout protection.
    
    Args:
        context_or_bot: Telegram Bot or Application context
        chat_id: Chat ID
        message_id: Message ID to edit
        text: New message text
        timeout: Timeout in seconds
        **kwargs: Additional arguments for edit_message_text
        
    Returns:
        Message object or None on timeout
    """
    try:
        if hasattr(context_or_bot, "bot"):
            bot = context_or_bot.bot
        else:
            bot = context_or_bot
        
        return await with_timeout(
            bot.edit_message_text,
            timeout,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            operation_name=f"edit_message(chat_id={chat_id}, message_id={message_id})",
            **kwargs,
        )
    except asyncio.TimeoutError:
        logger.error(
            "EDIT_MESSAGE_TIMEOUT chat_id=%s message_id=%s text_length=%s timeout=%.1fs",
            chat_id,
            message_id,
            len(text),
            timeout,
        )
        return None
    except Exception as exc:
        logger.error(
            "EDIT_MESSAGE_FAILED chat_id=%s message_id=%s error=%s",
            chat_id,
            message_id,
            exc,
            exc_info=True,
        )
        return None


async def answer_callback_safe(
    query: Any,
    text: Optional[str] = None,
    timeout: float = 10.0,
    **kwargs: Any,
) -> bool:
    """
    Answer callback query with timeout protection.
    
    Args:
        query: CallbackQuery object
        text: Optional text to show
        timeout: Timeout in seconds
        **kwargs: Additional arguments for answer
        
    Returns:
        True if successful, False otherwise
    """
    try:
        await with_timeout(
            query.answer,
            timeout,
            text=text,
            operation_name=f"answer_callback(query_id={query.id})",
            **kwargs,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning(
            "ANSWER_CALLBACK_TIMEOUT query_id=%s timeout=%.1fs",
            query.id,
            timeout,
        )
        return False
    except Exception as exc:
        logger.warning(
            "ANSWER_CALLBACK_FAILED query_id=%s error=%s",
            query.id,
            exc,
            exc_info=True,
        )
        return False
