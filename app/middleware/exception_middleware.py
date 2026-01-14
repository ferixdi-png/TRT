"""
Global exception middleware for aiogram.

Ensures NO SILENT FAILURES - all exceptions are logged with cid and user context.
"""
import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, CallbackQuery, Message

from app.telemetry.logging_contract import ReasonCode
from app.telemetry import log_callback_rejected, get_event_ids, generate_cid

logger = logging.getLogger(__name__)


class ExceptionMiddleware(BaseMiddleware):
    """
    Catch all unhandled exceptions in handlers.
    
    CRITICAL: This middleware ensures that:
    1. All exceptions are logged with full context (cid, user_id, update_id)
    2. User gets a safe error message (no stack traces)
    3. Callback queries are always answered (no infinite loading)
    4. Telemetry records INTERNAL_ERROR rejections
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Wrap handler execution with exception catching."""
        cid = data.get("cid")
        bot_state = data.get("bot_state")
        
        try:
            # Execute handler
            return await handler(event, data)
        
        except Exception as exc:
            # Generate CID if not provided
            if not cid:
                cid = generate_cid()
            
            # Use unified get_event_ids for safe extraction
            event_ids = get_event_ids(event, data)
            
            # Extract callback_data if available
            callback_data = None
            if isinstance(event, CallbackQuery):
                callback_data = getattr(event, 'data', None)
            elif isinstance(event, Update) and event.callback_query:
                callback_data = getattr(event.callback_query, 'data', None)
            
            event_type = type(event).__name__
            
            # Log with full context
            logger.error(
                f"[EXCEPTION_MIDDLEWARE] Unhandled exception in handler\n"
                f"cid={cid} user_id={event_ids.get('user_id')} chat_id={event_ids.get('chat_id')} update_id={event_ids.get('update_id')}\n"
                f"event_type={event_type} bot_state={bot_state}\n"
                f"Exception: {exc.__class__.__name__}: {exc}\n"
                f"{''.join(traceback.format_tb(exc.__traceback__))}"
            )
            
            # Log telemetry rejection with unified contract
            try:
                log_callback_rejected(
                    callback_data=callback_data,
                    reason_code=ReasonCode.INTERNAL_ERROR,
                    reason_detail=f"{exc.__class__.__name__}: {str(exc)[:200]}",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc)[:200],
                    cid=cid
                )
            except Exception as log_err:
                logger.error(f"[EXCEPTION_MIDDLEWARE] Failed to log telemetry: {log_err}")
            
            # Send safe error message to user
            try:
                if isinstance(event, CallbackQuery) or (isinstance(event, Update) and event.callback_query):
                    callback = event if isinstance(event, CallbackQuery) else event.callback_query
                    await callback.answer(
                        "❌ Произошла ошибка. Попробуйте /start",
                        show_alert=True
                    )
                    
                    # Try to edit message with error UI
                    if callback.message:
                        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                        
                        await callback.message.edit_text(
                            "❌ <b>Произошла ошибка</b>\n\n"
                            "Попробуйте обновить меню или обратитесь в поддержку.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔄 Главное меню", callback_data="main_menu")],
                                [InlineKeyboardButton(text="💬 Поддержка", callback_data="support")]
                            ])
                        )
                
                elif isinstance(event, Message) or (isinstance(event, Update) and event.message):
                    message = event if isinstance(event, Message) else event.message
                    await message.answer(
                        "❌ Произошла ошибка при обработке сообщения.\n"
                        "Попробуйте /start или обратитесь в поддержку."
                    )
            
            except Exception as send_error:
                logger.error(f"[EXCEPTION_MIDDLEWARE] Failed to send error message to user: {send_error}")
            
            # Re-raise to let aiogram know handler failed
            # (but user already got a safe message)
            raise


__all__ = ["ExceptionMiddleware"]
