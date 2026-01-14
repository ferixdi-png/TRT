"""
Global fallback handler for unknown callbacks.

CRITICAL: This handler MUST be registered LAST in dispatcher to catch all unhandled callbacks.
Ensures NO SILENT CLICKS - every callback gets a response.
"""
import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.telemetry import (
    log_callback_received,
    log_callback_rejected,
    generate_cid,
    get_event_ids,
)
from app.telemetry.logging_contract import ReasonCode

logger = logging.getLogger(__name__)

router = Router(name="fallback")


@router.callback_query(F.data)
async def fallback_unknown_callback(callback: CallbackQuery, data: dict = None, cid=None, bot_state=None):
    """
    Global fallback for unknown/unhandled callbacks.
    
    This handler catches ANY callback that wasn't matched by other routers.
    Logs UNKNOWN_CALLBACK and responds to user with actionable message.
    """
    # Generate CID if not provided
    if not cid:
        cid = generate_cid()
    
    # Use unified get_event_ids to safely extract all IDs
    event_ids = get_event_ids(callback, data or {})
    
    callback_data = callback.data or ""
    
    # Log telemetry with unified contract
    try:
        log_callback_received(
            callback_data=callback_data,
            query_id=event_ids.get("callback_id"),
            message_id=event_ids.get("message_id"),
            user_id=event_ids.get("user_id"),
            update_id=event_ids.get("update_id"),
            cid=cid
        )
        log_callback_rejected(
            callback_data=callback_data,
            reason_code=ReasonCode.UNKNOWN_CALLBACK,
            reason_detail=f"No handler for callback_data: {callback_data}",
            cid=cid
        )
    except Exception as e:
        logger.error(f"[FALLBACK] Failed to log telemetry: {e}", exc_info=True)
    
    # Log for debugging
    logger.warning(
        f"[FALLBACK] Unknown callback: data={callback_data} "
        f"user_id={event_ids.get('user_id')} chat_id={event_ids.get('chat_id')} cid={cid}"
    )
    
    # CRITICAL: Always answer callback to prevent "loading" state in Telegram
    await callback.answer(
        "⚠️ Эта кнопка устарела. Обновите меню: /start",
        show_alert=False
    )
    
    # Optionally send message with refresh button
    try:
        if callback.message:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            
            await callback.message.edit_text(
                "⚠️ <b>Кнопка устарела</b>\n\n"
                "Меню обновлено. Нажмите кнопку ниже для обновления:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить меню", callback_data="main_menu")]
                ])
            )
    except Exception as e:
        logger.debug(f"[FALLBACK] Could not edit message: {e}")


__all__ = ["router"]
