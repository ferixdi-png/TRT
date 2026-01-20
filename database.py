"""
Database module (disabled).
All DB operations are no-ops in github-only storage mode.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional, Iterator

logger = logging.getLogger(__name__)

DB_DISABLED_MESSAGE = "DB_DISABLED: github-only mode"


def _log_disabled(action: str) -> None:
    logger.info("%s action=%s", DB_DISABLED_MESSAGE, action)


def is_database_configured() -> bool:
    _log_disabled("is_database_configured")
    return False


def get_connection_pool() -> None:
    _log_disabled("get_connection_pool")
    return None


class _DummyCursor:
    def execute(self, *_args, **_kwargs) -> None:
        _log_disabled("cursor.execute")

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _DummyConnection:
    def cursor(self, *args, **kwargs) -> _DummyCursor:
        return _DummyCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


@contextmanager
def get_db_connection() -> Iterator[_DummyConnection]:
    _log_disabled("get_db_connection")
    yield _DummyConnection()


def init_database() -> None:
    _log_disabled("init_database")


def get_or_create_user(user_id: int) -> Dict[str, Any]:
    _log_disabled("get_or_create_user")
    return {"id": user_id, "balance": 0.0}


def get_user_balance(user_id: int) -> Decimal:
    _log_disabled("get_user_balance")
    return Decimal("0")


def update_user_balance(user_id: int, new_balance: Decimal) -> bool:
    _log_disabled("update_user_balance")
    return False


def add_to_balance(user_id: int, amount: Decimal) -> bool:
    _log_disabled("add_to_balance")
    return False


def create_operation(
    user_id: int,
    operation_type: str,
    amount: Decimal,
    model: Optional[str] = None,
    result_url: Optional[str] = None,
    prompt: Optional[str] = None,
) -> Optional[int]:
    _log_disabled("create_operation")
    return None


def get_user_operations(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    operation_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    _log_disabled("get_user_operations")
    return []


def log_kie_operation(*_args, **_kwargs) -> None:
    _log_disabled("log_kie_operation")


def log_debug(*_args, **_kwargs) -> None:
    _log_disabled("log_debug")


def get_database_size() -> Dict[str, Any]:
    _log_disabled("get_database_size")
    return {}
