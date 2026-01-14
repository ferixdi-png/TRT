"""
Telemetry Middleware for aiogram - adds correlation ID and bot state to all updates.

CRITICAL: This middleware must be fail-safe - if telemetry fails, app should still work.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.telemetry.events import generate_cid, log_update_received
from app.telemetry.telemetry_helpers import get_update_id, get_user_id, get_chat_id
from app.utils.runtime_state import runtime_state

logger = logging.getLogger(__name__)


class TelemetryMiddleware(BaseMiddleware):
    """
    Middleware that adds correlation ID (cid) and bot state to all updates.
    
    CRITICAL: Fail-safe - if telemetry logging fails, app continues normally.
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Process update: add cid and bot_state, log UPDATE_RECEIVED.
        
        Fail-safe: any telemetry errors are logged but don't break the flow.
        """
        # Generate correlation ID
        cid = generate_cid()
        
        # Add cid to data context (available to all handlers)
        data["cid"] = cid
        
        # Add bot state (ACTIVE/PASSIVE)
        data["bot_state"] = "ACTIVE" if runtime_state.lock_acquired else "PASSIVE"
        
        # Extract context safely
        try:
            update_id = get_update_id(event, data)
            user_id = get_user_id(event)
            chat_id = get_chat_id(event)
        except Exception as e:
            logger.debug(f"Failed to extract telemetry context: {e}")
            update_id = None
            user_id = None
            chat_id = None
        
        # Log UPDATE_RECEIVED (fail-safe: don't break if logging fails)
        try:
            log_update_received(
                update_id=update_id,
                user_id=user_id,
                chat_id=chat_id,
                cid=cid,
                bot_state=data["bot_state"]
            )
        except Exception as e:
            logger.warning(f"Telemetry logging failed (non-critical): {e}")
        
        # Continue to handler
        try:
            result = await handler(event, data)
            
            # Log DISPATCH_OK (fail-safe)
            try:
                from app.telemetry.events import log_dispatch_ok
                log_dispatch_ok(cid=cid)
            except Exception as e:
                logger.debug(f"Failed to log DISPATCH_OK: {e}")
            
            return result
            
        except Exception as e:
            # Log DISPATCH_FAIL (fail-safe)
            # Note: log_dispatch_fail may not exist, use log_callback_rejected as fallback
            try:
                from app.telemetry.events import log_dispatch_ok, log_callback_rejected
                from app.telemetry.logging_contract import ReasonCode
                # Try to log as dispatch fail, fallback to callback_rejected
                try:
                    if hasattr(log_callback_rejected, '__call__'):
                        log_callback_rejected(
                            cid=cid,
                            reason_code=ReasonCode.INTERNAL_ERROR,
                            reason_detail=f"{type(e).__name__}: {str(e)[:200]}"
                        )
                except Exception:
                    pass  # Even logging failed, continue
            except Exception as log_err:
                logger.debug(f"Failed to log dispatch failure: {log_err}")
            
            # Re-raise to let exception middleware handle it
            raise

