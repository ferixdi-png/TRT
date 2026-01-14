"""
Telemetry helper functions for safe attribute access and context extraction.

NOTE: TelemetryMiddleware class is in app/telemetry/middleware.py
"""

# Backward compatibility: re-export TelemetryMiddleware from middleware module
try:
    from app.telemetry.middleware import TelemetryMiddleware
    __all__ = [
        "get_update_id",
        "get_callback_id",
        "get_user_id",
        "get_chat_id",
        "get_message_id",
        "safe_answer_callback",
        "TelemetryMiddleware",  # Re-export for backward compatibility
    ]
except ImportError:
    # If middleware module is not available, TelemetryMiddleware will be None
    # This allows fail-open behavior
    TelemetryMiddleware = None
    __all__ = [
        "get_update_id",
        "get_callback_id",
        "get_user_id",
        "get_chat_id",
        "get_message_id",
        "safe_answer_callback",
    ]

from typing import Optional, Any, Dict
from aiogram.types import TelegramObject, Update, CallbackQuery, Message


def get_update_id(event: TelegramObject, data: Dict[str, Any]) -> Optional[int]:
    """
    Safely extract update_id from event or data context.
    
    Args:
        event: Telegram event (Update, CallbackQuery, Message, etc.)
        data: Handler data dict from aiogram middleware
        
    Returns:
        update_id if found, None otherwise
    """
    try:
        # Try to get from data context first (aiogram 3.x style)
        if "event_update" in data:
            update = data["event_update"]
            if hasattr(update, 'update_id'):
                return update.update_id
        
        # Try legacy "update" key
        if "update" in data:
            update = data["update"]
            if hasattr(update, 'update_id'):
                return update.update_id
        
        # Try event itself if it's an Update
        if isinstance(event, Update):
            return getattr(event, 'update_id', None)
        
        # For CallbackQuery, we don't have update_id directly
        # Return None - caller should use callback.id instead
        return None
    except Exception:
        return None


def get_callback_id(event: TelegramObject) -> Optional[str]:
    """
    Extract callback query ID from event.
    
    Args:
        event: Telegram event
        
    Returns:
        callback query ID if event is CallbackQuery, None otherwise
    """
    try:
        if isinstance(event, CallbackQuery):
            return event.id
        return None
    except Exception:
        return None


def get_user_id(event: TelegramObject) -> Optional[int]:
    """
    Safely extract user_id from event.
    
    Args:
        event: Telegram event
        
    Returns:
        user_id if found, None otherwise
    """
    try:
        if isinstance(event, CallbackQuery):
            if event.from_user:
                return event.from_user.id
        elif isinstance(event, Message):
            if event.from_user:
                return event.from_user.id
        elif isinstance(event, Update):
            if event.message and event.message.from_user:
                return event.message.from_user.id
            elif event.callback_query and event.callback_query.from_user:
                return event.callback_query.from_user.id
        return None
    except Exception:
        return None


def get_chat_id(event: TelegramObject) -> Optional[int]:
    """
    Safely extract chat_id from event.
    
    Args:
        event: Telegram event
        
    Returns:
        chat_id if found, None otherwise
    """
    try:
        if isinstance(event, CallbackQuery):
            if event.message:
                return event.message.chat.id
        elif isinstance(event, Message):
            return event.chat.id
        elif isinstance(event, Update):
            if event.message:
                return event.message.chat.id
            elif event.callback_query and event.callback_query.message:
                return event.callback_query.message.chat.id
        return None
    except Exception:
        return None


def get_message_id(event: TelegramObject) -> Optional[int]:
    """
    Safely extract message_id from event.
    
    Args:
        event: Telegram event
        
    Returns:
        message_id if found, None otherwise
    """
    try:
        if isinstance(event, CallbackQuery):
            if event.message:
                return event.message.message_id
        elif isinstance(event, Message):
            return event.message_id
        elif isinstance(event, Update):
            if event.message:
                return event.message.message_id
            elif event.callback_query and event.callback_query.message:
                return event.callback_query.message.message_id
        return None
    except Exception:
        return None


async def safe_answer_callback(
    callback: CallbackQuery,
    text: Optional[str] = None,
    show_alert: bool = False,
    logger_instance: Optional[Any] = None
) -> bool:
    """
    Safely answer a callback query, preventing infinite spinner.
    
    CRITICAL: This function MUST NOT raise exceptions.
    It handles all errors gracefully to prevent "eternal loading" in Telegram.
    
    Args:
        callback: CallbackQuery to answer
        text: Optional text to show (toast or alert)
        show_alert: If True, show as alert popup; if False, show as toast
        logger_instance: Optional logger instance for error logging
        
    Returns:
        True if answered successfully, False otherwise
    """
    import logging
    
    if logger_instance is None:
        logger_instance = logging.getLogger(__name__)
    
    if callback is None:
        logger_instance.debug("[SAFE_ANSWER] Callback is None, skipping")
        return False
    
    try:
        # Try to answer via callback.answer() method (aiogram 3.x)
        if hasattr(callback, 'answer') and callable(callback.answer):
            await callback.answer(text=text, show_alert=show_alert)
            return True
    except Exception as e:
        # Log but don't fail - try alternative method
        logger_instance.debug(f"[SAFE_ANSWER] callback.answer() failed: {e}")
    
    # Fallback: try via bot.answer_callback_query if callback has bot reference
    try:
        if hasattr(callback, 'bot') and callback.bot:
            if hasattr(callback.bot, 'answer_callback_query'):
                await callback.bot.answer_callback_query(
                    callback_query_id=callback.id,
                    text=text,
                    show_alert=show_alert
                )
                return True
    except Exception as e:
        logger_instance.warning(f"[SAFE_ANSWER] bot.answer_callback_query() failed: {e}")
    
    # Ultimate fallback: if callback has id, try direct API call
    try:
        if hasattr(callback, 'id') and callback.id:
            # This is a last resort - we don't have bot instance
            # Log warning but don't crash
            logger_instance.warning(
                f"[SAFE_ANSWER] Could not answer callback {callback.id}: "
                f"no working method available"
            )
    except Exception:
        pass  # Even logging failed, just give up
    
    return False
