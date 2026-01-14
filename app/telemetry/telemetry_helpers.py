"""
Telemetry helper functions for safe attribute access and context extraction.
"""

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


def get_event_ids(event: TelegramObject, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely extract all event IDs for telemetry correlation.
    
    This is the UNIFIED function to get all IDs at once, preventing
    AttributeError from accessing non-existent attributes.
    
    Args:
        event: Telegram event (Update, CallbackQuery, Message, etc.)
        data: Handler data dict from aiogram middleware
        
    Returns:
        Dict with keys: update_id, callback_id, message_id, user_id, chat_id
        All values are Optional[int] or Optional[str]
    """
    result = {
        "update_id": None,
        "callback_id": None,
        "message_id": None,
        "user_id": None,
        "chat_id": None,
    }
    
    try:
        # Get update_id (from Update context, not from CallbackQuery)
        result["update_id"] = get_update_id(event, data)
        
        # Get callback_id (only for CallbackQuery)
        result["callback_id"] = get_callback_id(event)
        
        # Get message_id
        result["message_id"] = get_message_id(event)
        
        # Get user_id
        result["user_id"] = get_user_id(event)
        
        # Get chat_id
        result["chat_id"] = get_chat_id(event)
        
    except Exception:
        # Fail-safe: return what we have
        pass
    
    return result
