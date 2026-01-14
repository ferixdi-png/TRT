"""
Global error handler - user-friendly error messages.
Contract: All errors caught, user always gets response with keyboard (no dead ends).
"""
from aiogram import Router
from aiogram.types import ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup
import logging

logger = logging.getLogger(__name__)

router = Router(name="error_handler")


def _error_fallback_keyboard() -> InlineKeyboardMarkup:
    """Fallback keyboard for error messages - always provide navigation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            [InlineKeyboardButton(text="❓ Поддержка", callback_data="menu:support")],
        ]
    )


@router.error()
async def global_error_handler(event: ErrorEvent):
    """
    Global error handler - always respond to user.
    
    Contract:
    - User gets friendly message (no stacktrace)
    - Suggests /start as next step
    - Never silent
    """
    exception = event.exception
    update = event.update
    
    # Детальное логирование для диагностики
    user_id = None
    username = None
    error_context = {}
    
    if update.message:
        user_id = update.message.from_user.id
        username = update.message.from_user.username
        error_context = {
            "message_id": update.message.message_id,
            "text": update.message.text[:100] if update.message.text else None,
            "chat_id": update.message.chat.id
        }
    elif update.callback_query:
        user_id = update.callback_query.from_user.id
        username = update.callback_query.from_user.username
        error_context = {
            "callback_data": update.callback_query.data,
            "message_id": update.callback_query.message.message_id if update.callback_query.message else None
        }
    
    # Расширенное логирование с контекстом
    logger.error(
        f"🔴 ERROR | Update {update.update_id} | "
        f"User {user_id} (@{username}) | "
        f"Type: {type(exception).__name__} | "
        f"Message: {str(exception)[:200]} | "
        f"Context: {error_context}",
        exc_info=exception,
        extra={
            "update_id": update.update_id,
            "user_id": user_id,
            "username": username,
            "error_type": type(exception).__name__,
            "context": error_context
        }
    )
    
    # User-friendly error message (no stacktrace)
    # Определяем тип ошибки для более понятного сообщения
    if "timeout" in str(exception).lower():
        error_message = (
            "⏱ <b>Превышено время ожидания</b>\n\n"
            "Сервер слишком долго отвечает. Попробуйте:\n"
            "• Подождать минуту и повторить\n"
            "• Выбрать другую модель\n"
            "• Нажать /start для главного меню"
        )
    elif "network" in str(exception).lower() or "connection" in str(exception).lower():
        error_message = (
            "🌐 <b>Проблема с подключением</b>\n\n"
            "Не удалось связаться с сервером.\n\n"
            "Попробуйте через минуту или нажмите /start"
        )
    else:
        error_message = (
            "⚠️ <b>Произошла ошибка</b>\n\n"
            "Мы уже работаем над исправлением.\n\n"
            "💡 <b>Попробуйте:</b>\n"
            "• Повторить действие\n"
            "• Нажать /start для главного меню\n"
            "• Обратиться в поддержку, если проблема повторяется"
        )
    
    # Always provide keyboard to avoid dead ends
    keyboard = _error_fallback_keyboard()
    
    # Determine update type and respond accordingly
    try:
        if update.message:
            await update.message.answer(error_message, reply_markup=keyboard)
        elif update.callback_query:
            callback = update.callback_query
            await callback.answer("⚠️ Ошибка")
            try:
                await callback.message.answer(error_message, reply_markup=keyboard)
            except Exception as msg_err:
                # If edit fails, try to send new message (catch Telegram API errors)
                # MASTER PROMPT: No bare except - catch Exception for Telegram API failures
                logger.debug(f"Failed to send error message via callback: {msg_err}")
                try:
                    await callback.message.answer(error_message, reply_markup=keyboard)
                except Exception as retry_err:
                    logger.debug(f"Retry also failed: {retry_err}")
                    pass
        elif update.edited_message:
            await update.edited_message.answer(error_message, reply_markup=keyboard)
    except Exception as e:
        # Last resort - log but don't crash
        logger.critical(f"Failed to send error message to user: {e}")
    
    # Don't re-raise - we've handled it
    return True
