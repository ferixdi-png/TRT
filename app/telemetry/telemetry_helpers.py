"""
Логирование обработки callback_query и message.

Цель: создать полную цепочку событий для диагностики "почему кнопка не работает".

Цепочка для callback:
  CALLBACK_RECEIVED → CALLBACK_ROUTED → CALLBACK_ACCEPTED/REJECTED/NOOP → ANSWER_CALLBACK_QUERY

Используется middleware для автоматического tracking.
"""

import logging
from typing import Optional, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Update, User, Chat
from app.telemetry.logging_contract import (
    log_event,
    new_correlation_id,
    ReasonCode,
    EventType,
    Domain,
    BotState,
    LatencyTracker,
)
from app.telemetry.ui_registry import ScreenId, ButtonId, UIMap

logger = logging.getLogger(__name__)


class TelemetryMiddleware(BaseMiddleware):
    """
    Middleware для автоматического логирования жизненного цикла update.
    Добавляет correlation_id и bot_state в контекст.
    """
    
    async def __call__(self, handler, event: Update, data: Dict[str, Any]):
        # Создать correlation_id для всей цепочки
        cid = new_correlation_id()
        data["cid"] = cid
        
        # Определить bot_state из конфига (потом будет передаваться)
        bot_state = data.get("bot_state", BotState.ACTIVE)
        data["bot_state"] = bot_state
        
        # Логировать тип события
        event_type = None
        update_id = event.update_id
        user_id = None
        chat_id = None
        
        if event.message:
            event_type = EventType.MESSAGE
            user_id = event.message.from_user.id
            chat_id = event.message.chat.id
        elif event.callback_query:
            event_type = EventType.CALLBACK_QUERY
            user_id = event.callback_query.from_user.id
            chat_id = event.callback_query.message.chat.id
        elif event.pre_checkout_query:
            event_type = EventType.PRE_CHECKOUT
            user_id = event.pre_checkout_query.from_user.id
        
        # RECEIVED event
        if event_type:
            log_event(
                "UPDATE_RECEIVED",
                correlation_id=cid,
                event_type=event_type,
                update_id=update_id,
                user_id=user_id,
                chat_id=chat_id,
                bot_state=bot_state,
                domain=Domain.UX,
            )
        
        # Выполнить handler
        try:
            result = await handler(event, data)
            
            # DISPATCH_OK event
            log_event(
                "DISPATCH_OK",
                correlation_id=cid,
                event_type=event_type,
                update_id=update_id,
                user_id=user_id,
                chat_id=chat_id,
                domain=Domain.QUEUE,
                result="accepted",
            )
            
            return result
        except Exception as e:
            log_event(
                "DISPATCH_FAIL",
                correlation_id=cid,
                event_type=event_type,
                update_id=update_id,
                user_id=user_id,
                chat_id=chat_id,
                domain=Domain.QUEUE,
                result="failed",
                error_type=type(e).__name__,
                error_message=str(e)[:200],  # Обрезать для безопасности
            )
            raise


def log_callback_received(
    cid: str,
    update_id: int,
    user_id: int,
    chat_id: int,
    callback_data: str,
    bot_state: str,
) -> None:
    """Логировать получение callback_query."""
    
    log_event(
        "CALLBACK_RECEIVED",
        correlation_id=cid,
        event_type=EventType.CALLBACK_QUERY,
        update_id=update_id,
        user_id=user_id,
        chat_id=chat_id,
        bot_state=bot_state,
        domain=Domain.UX,
        payload_sanitized=callback_data[:100],  # Первые 100 chars
    )


def log_callback_routed(
    cid: str,
    user_id: int,
    chat_id: int,
    handler: str,
    action_id: str,
    button_id: Optional[str] = None,
) -> None:
    """Логировать, что callback распарсился и идёт в handler."""
    
    log_event(
        "CALLBACK_ROUTED",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        handler=handler,
        action_id=action_id,
        button_id=button_id,
        domain=Domain.UX,
        result="routed",
    )


def log_callback_rejected(
    cid: str,
    user_id: int,
    chat_id: int,
    reason_code: str,
    reason_text: str,
    expected_state: Optional[str] = None,
    actual_state: Optional[str] = None,
    bot_state: Optional[str] = None,
) -> None:
    """Логировать отказ callback (STATE_MISMATCH, PASSIVE_REJECT и т.д.)."""
    
    log_event(
        "CALLBACK_REJECTED",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        result="rejected",
        reason_code=reason_code,
        reason_text=reason_text,
        domain=Domain.UX,
        bot_state=bot_state,
        extra={
            "expected_state": expected_state,
            "actual_state": actual_state,
        } if (expected_state or actual_state) else None,
    )


def log_callback_accepted(
    cid: str,
    user_id: int,
    chat_id: int,
    next_screen: Optional[str] = None,
    action_id: Optional[str] = None,
) -> None:
    """Логировать успешную обработку callback."""
    
    log_event(
        "CALLBACK_ACCEPTED",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        result="accepted",
        screen_id=next_screen,
        action_id=action_id,
        domain=Domain.UX,
    )


def log_callback_noop(
    cid: str,
    user_id: int,
    chat_id: int,
    reason_code: str,
    reason_text: str,
) -> None:
    """Логировать no-op callback (обычно OK, просто игнорирование)."""
    
    log_event(
        "CALLBACK_NOOP",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        result="noop",
        reason_code=reason_code,
        reason_text=reason_text,
        domain=Domain.UX,
    )


def log_ui_render(
    cid: str,
    user_id: int,
    chat_id: int,
    screen_id: str,
    buttons: list,
) -> None:
    """Логировать отправку экрана (UI_RENDER)."""
    
    log_event(
        "UI_RENDER",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        screen_id=screen_id,
        domain=Domain.UX,
        extra={
            "buttons_count": len(buttons),
            "buttons": buttons[:5],  # Первые 5 кнопок
        },
    )


def log_param_input(
    cid: str,
    user_id: int,
    chat_id: int,
    param_name: str,
    value: str,
    source: str = "text",  # button или text
) -> None:
    """Логировать ввод параметра."""
    
    log_event(
        "PARAM_INPUT_RECEIVED",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        domain=Domain.MODEL,
        extra={
            "param_name": param_name,
            "value": value[:100],  # Обрезать
            "source": source,
        },
    )


def log_param_validation_failed(
    cid: str,
    user_id: int,
    chat_id: int,
    param_name: str,
    reason_code: str,
    hint_to_user: str,
) -> None:
    """Логировать ошибку валидации параметра."""
    
    log_event(
        "PARAM_VALIDATION_FAILED",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        domain=Domain.MODEL,
        result="rejected",
        reason_code=reason_code,
        reason_text=hint_to_user,
        extra={
            "param_name": param_name,
        },
    )


def log_answer_callback_query(
    cid: str,
    user_id: int,
    chat_id: int,
    text: str,
    show_alert: bool = False,
) -> None:
    """Логировать ответ callback_query пользователю."""
    
    log_event(
        "ANSWER_CALLBACK_QUERY",
        correlation_id=cid,
        user_id=user_id,
        chat_id=chat_id,
        domain=Domain.UX,
        extra={
            "text": text[:100],
            "show_alert": show_alert,
        },
    )


def log_queue_enqueue(
    cid: str,
    update_id: int,
    event_type: str,
    queue_size: int,
) -> None:
    """Логировать попадание update в очередь."""
    
    log_event(
        "ENQUEUE",
        correlation_id=cid,
        update_id=update_id,
        domain=Domain.QUEUE,
        event_type=event_type,
        extra={
            "queue_size": queue_size,
        },
    )


def log_queue_pick(
    cid: str,
    worker_id: str,
) -> None:
    """Логировать что worker взял update из очереди."""
    
    log_event(
        "WORKER_PICK",
        correlation_id=cid,
        domain=Domain.QUEUE,
        extra={
            "worker_id": worker_id,
        },
    )


def log_dispatch_start(cid: str) -> LatencyTracker:
    """Логировать начало обработки в handler. Возвращает tracker для измерения latency."""
    
    log_event(
        "DISPATCH_START",
        correlation_id=cid,
        domain=Domain.QUEUE,
    )
    
    return LatencyTracker()


def log_dispatch_ok(
    cid: str,
    latency_tracker: LatencyTracker,
) -> None:
    """Логировать успешное завершение обработки."""
    
    log_event(
        "DISPATCH_OK",
        correlation_id=cid,
        domain=Domain.QUEUE,
        result="accepted",
        latency_ms=latency_tracker.elapsed_ms(),
    )


def log_dispatch_fail(
    cid: str,
    latency_tracker: LatencyTracker,
    error_type: str,
    error_message: str,
) -> None:
    """Логировать ошибку во время обработки."""
    
    log_event(
        "DISPATCH_FAIL",
        correlation_id=cid,
        domain=Domain.QUEUE,
        result="failed",
        error_type=error_type,
        error_message=error_message[:200],
        latency_ms=latency_tracker.elapsed_ms(),
    )
