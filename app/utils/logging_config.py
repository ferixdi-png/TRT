"""
Унифицированная конфигурация логирования
Единый логгер, уровни, формат, request-id для операций генерации
"""

import logging
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable для request-id (для async операций)
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


def get_request_id() -> Optional[str]:
    """Получить текущий request-id"""
    return _request_id.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """Установить request-id (генерирует новый если не указан)"""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    _request_id.set(request_id)
    return request_id


class RequestIdFilter(logging.Filter):
    """Фильтр для добавления request-id в логи"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        if request_id:
            record.request_id = request_id
        else:
            record.request_id = "-"
        return True


class RedactTelegramTokenFilter(logging.Filter):
    """Редактирует токены Telegram в логах, чтобы не утекали URL с bot<token>."""

    TOKEN_PATTERN = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.TOKEN_PATTERN.sub("bot<REDACTED>", record.msg)
        # Редактируем также args для форматированных логов (httpx использует %s)
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    self.TOKEN_PATTERN.sub("bot<REDACTED>", str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: self.TOKEN_PATTERN.sub("bot<REDACTED>", str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
        return True


def setup_logging(level: int = logging.INFO, include_request_id: bool = True) -> None:
    """
    Настраивает унифицированное логирование
    
    Args:
        level: Уровень логирования
        include_request_id: Включать ли request-id в формат
    """
    # Формат с request-id
    if include_request_id:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s'
    else:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Создаем console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # Добавляем фильтр для request-id и редактирования токена
    if include_request_id:
        console_handler.addFilter(RequestIdFilter())
    console_handler.addFilter(RedactTelegramTokenFilter())
    
    root_logger.addHandler(console_handler)
    
    # Настраиваем уровни для внешних библиотек
    httpx_logger = logging.getLogger('httpx')
    httpx_logger.setLevel(logging.WARNING)
    httpx_logger.addFilter(RedactTelegramTokenFilter())
    httpcore_logger = logging.getLogger('httpcore')
    httpcore_logger.setLevel(logging.WARNING)
    httpcore_logger.addFilter(RedactTelegramTokenFilter())
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер с унифицированным именем
    
    Args:
        name: Имя логгера (обычно __name__)
    
    Returns:
        Настроенный логгер
    """
    return logging.getLogger(name)


def log_error_with_stacktrace(logger: logging.Logger, error: Exception, user_message: str = "Ошибка, попробуйте ещё раз") -> None:
    """
    Логирует ошибку с полным stacktrace в логах
    
    Args:
        logger: Логгер
        error: Исключение
        user_message: Короткое сообщение для пользователя (не логируется)
    """
    logger.error(
        f"Error: {type(error).__name__}: {error}",
        exc_info=True  # Включает полный stacktrace
    )
    # user_message не логируется - оно отправляется пользователю отдельно


def log_generation_operation(logger: logging.Logger, operation: str, user_id: int, model_id: str = None, **kwargs) -> None:
    """
    Логирует операцию генерации с request-id
    
    Args:
        logger: Логгер
        operation: Название операции (start, complete, error, etc.)
        user_id: ID пользователя
        model_id: ID модели (опционально)
        **kwargs: Дополнительные параметры для логирования
    """
    request_id = get_request_id() or set_request_id()
    
    log_parts = [f"GEN[{operation}]", f"user_id={user_id}"]
    if model_id:
        log_parts.append(f"model_id={model_id}")
    if kwargs:
        log_parts.extend([f"{k}={v}" for k, v in kwargs.items()])
    
    logger.info(" | ".join(log_parts))
