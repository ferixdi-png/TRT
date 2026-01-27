"""
Безопасные обработчики с graceful exception handling.
Предотвращают "тихие" падения и обеспечивают информативные ответы.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class SafeHandlerError(Exception):
    """Базовый класс для ошибок безопасных обработчиков."""
    pass


async def safe_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    handler_func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]],
    error_message: str = "❌ Ошибка сервера, попробуйте позже"
) -> Any:
    """
    Безопасная обертка для callback обработчиков.
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
        handler_func: Основная функция обработчика
        error_message: Сообщение об ошибке для пользователя
        
    Returns:
        Результат handler_func или None в случае ошибки
    """
    try:
        return await handler_func(update, context)
    except asyncio.TimeoutError as e:
        logger.error(f"Callback timeout: {e}", exc_info=True)
        await _send_error_response(update, "⏰ Запрос занял слишком много времени")
        return None
    except SafeHandlerError as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        await _send_error_response(update, error_message)
        return None
    except Exception as e:
        logger.error(f"Unexpected callback error: {e}", exc_info=True)
        await _send_error_response(update, error_message)
        return None


async def safe_command_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    handler_func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]],
    error_message: str = "❌ Ошибка выполнения команды"
) -> Any:
    """
    Безопасная обертка для command обработчиков.
    
    Args:
        update: Telegram Update объект
        context: Telegram Context объект
        handler_func: Основная функция обработчика
        error_message: Сообщение об ошибке для пользователя
        
    Returns:
        Результат handler_func или None в случае ошибки
    """
    try:
        return await handler_func(update, context)
    except asyncio.TimeoutError as e:
        logger.error(f"Command timeout: {e}", exc_info=True)
        await _send_error_response(update, "⏰ Команда выполняется слишком долго")
        return None
    except SafeHandlerError as e:
        logger.error(f"Command error: {e}", exc_info=True)
        await _send_error_response(update, error_message)
        return None
    except Exception as e:
        logger.error(f"Unexpected command error: {e}", exc_info=True)
        await _send_error_response(update, error_message)
        return None


async def safe_api_call(
    api_func: Callable[..., Awaitable[Any]],
    *args,
    timeout: float = 30.0,
    error_message: str = "❌ Ошибка внешнего сервиса",
    **kwargs
) -> Any:
    """
    Безопасная обертка для API вызовов с таймаутом.
    
    Args:
        api_func: Асинхронная функция API
        timeout: Таймаут в секундах
        error_message: Сообщение об ошибке
        *args, **kwargs: Аргументы для api_func
        
    Returns:
        Результат API вызова или None в случае ошибки
    """
    try:
        return await asyncio.wait_for(api_func(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        logger.error(f"API timeout: {e}", exc_info=True)
        raise SafeHandlerError(error_message)
    except Exception as e:
        logger.error(f"API error: {e}", exc_info=True)
        raise SafeHandlerError(error_message)


async def safe_database_operation(
    db_func: Callable[..., Awaitable[Any]],
    *args,
    timeout: float = 10.0,
    error_message: str = "❌ Ошибка базы данных",
    **kwargs
) -> Any:
    """
    Безопасная обертка для операций с базой данных.
    
    Args:
        db_func: Асинхронная функция БД
        timeout: Таймаут в секундах
        error_message: Сообщение об ошибке
        *args, **kwargs: Аргументы для db_func
        
    Returns:
        Результат операции или None в случае ошибки
    """
    try:
        return await asyncio.wait_for(db_func(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        logger.error(f"Database timeout: {e}", exc_info=True)
        raise SafeHandlerError(error_message)
    except Exception as e:
        logger.error(f"Database error: {e}", exc_info=True)
        raise SafeHandlerError(error_message)


async def _send_error_response(update: Update, message: str) -> None:
    """
    Отправляет сообщение об ошибке пользователю.
    
    Args:
        update: Telegram Update объект
        message: Сообщение об ошибке
    """
    try:
        if update.callback_query:
            await update.callback_query.answer(message, show_alert=True)
        elif update.message:
            await update.message.reply_text(message)
        else:
            logger.warning(f"Cannot send error response: no message or callback_query")
    except Exception as e:
        logger.error(f"Failed to send error response: {e}", exc_info=True)


def safe_extract_user_id(update: Update) -> Optional[int]:
    """
    Безопасно извлекает user_id из update.
    
    Args:
        update: Telegram Update объект
        
    Returns:
        User ID или None если не найден
    """
    try:
        if update.callback_query and update.callback_query.from_user:
            return update.callback_query.from_user.id
        elif update.message and update.message.from_user:
            return update.message.from_user.id
        elif update.inline_query and update.inline_query.from_user:
            return update.inline_query.from_user.id
        return None
    except Exception as e:
        logger.error(f"Failed to extract user_id: {e}")
        return None


def safe_extract_chat_id(update: Update) -> Optional[int]:
    """
    Безопасно извлекает chat_id из update.
    
    Args:
        update: Telegram Update объект
        
    Returns:
        Chat ID или None если не найден
    """
    try:
        if update.callback_query and update.callback_query.message:
            return update.callback_query.message.chat_id
        elif update.message:
            return update.message.chat_id
        return None
    except Exception as e:
        logger.error(f"Failed to extract chat_id: {e}")
        return None


class GracefulDegradation:
    """Менеджер graceful degradation для внешних сервисов."""
    
    def __init__(self):
        self._service_status = {}
        self._fallback_messages = {
            "kie_api": "🎨 Сервис генерации временно недоступен. Попробуйте позже.",
            "database": "📊 База данных временно недоступна. Попробуйте позже.",
            "redis": "⚡ Кэш-сервис недоступен. Работаем в режиме пониженной производительности.",
            "storage": "💾 Хранилище недоступно. Некоторые функции могут не работать."
        }
    
    def mark_service_down(self, service_name: str) -> None:
        """Отмечает сервис как недоступный."""
        self._service_status[service_name] = False
        logger.warning(f"Service {service_name} marked as down")
    
    def mark_service_up(self, service_name: str) -> None:
        """Отмечает сервис как доступный."""
        self._service_status[service_name] = True
        logger.info(f"Service {service_name} marked as up")
    
    def is_service_available(self, service_name: str) -> bool:
        """Проверяет доступность сервиса."""
        return self._service_status.get(service_name, True)
    
    def get_fallback_message(self, service_name: str) -> str:
        """Возвращает fallback сообщение для сервиса."""
        return self._fallback_messages.get(service_name, "⚠️ Сервис временно недоступен")


# Глобальный экземпляр для graceful degradation
degradation_manager = GracefulDegradation()
