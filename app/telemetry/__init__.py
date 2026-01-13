"""
Telemetry пакет - единый стандарт логирования для инструментируемого продукта.

Модули:
- logging_contract: Основной контракт (log_event, ReasonCode, EventType, Domain)
- ui_registry: SSOT для экранов, кнопок, переходов
- telemetry_helpers: Хелперы для логирования (callback, dispatch, queue, UI)
"""

from app.telemetry.logging_contract import (
    log_event,
    new_correlation_id,
    hash_user_id,
    hash_chat_id,
    ReasonCode,
    EventType,
    Domain,
    BotState,
    LatencyTracker,
)
from app.telemetry.ui_registry import (
    ScreenId,
    ButtonId,
    FlowId,
    FlowStep,
    UIMap,
)

__all__ = [
    "log_event",
    "new_correlation_id",
    "hash_user_id",
    "hash_chat_id",
    "ReasonCode",
    "EventType",
    "Domain",
    "BotState",
    "LatencyTracker",
    "ScreenId",
    "ButtonId",
    "FlowId",
    "FlowStep",
    "UIMap",
]
