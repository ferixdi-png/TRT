"""Compatibility shim exposing a singleton db_service handle.

Some modules (webhook health endpoints, legacy tests) import
``app.database.service.db_service`` directly. Historically this module
existed; to avoid import errors and keep a single source of truth we now
proxy to :mod:`app.database.services` and mirror the default service
there.
"""
from __future__ import annotations

from typing import Optional

from app.database.services import DatabaseService, set_default_db_service

# Public singleton (legacy contract)
db_service: Optional[DatabaseService] = None


def configure_db_service(service: Optional[DatabaseService]) -> None:
    """Set the global db_service handle and sync default helper.

    Args:
        service: DatabaseService instance or None when DB is disabled.
    """
    global db_service
    db_service = service
    set_default_db_service(service)


def get_db_service() -> Optional[DatabaseService]:
    """Return configured DatabaseService (or None if not initialized)."""
    return db_service

__all__ = ["db_service", "configure_db_service", "get_db_service", "DatabaseService"]
