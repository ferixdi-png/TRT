"""Storage factory for PostgreSQL backend."""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.postgres_storage import PostgresStorage

logger = logging.getLogger(__name__)

_storage_instance: Optional[BaseStorage] = None


def _resolve_mode(_: Optional[str]) -> str:
    return "postgres"


def create_storage(
    storage_mode: Optional[str] = None,
    database_url: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> BaseStorage:
    """Create storage instance based on env."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    _ = _resolve_mode(storage_mode)
    database_url = database_url or os.getenv("DATABASE_URL", "").strip() or None

    if not database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL storage")
    partner_id = os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or ""
    if not partner_id:
        raise RuntimeError("BOT_INSTANCE_ID is required for multi-tenant storage")
    storage = PostgresStorage(database_url, partner_id=partner_id)

    _storage_instance = storage
    logger.info("[STORAGE] backend=postgres partner_id=%s", partner_id)
    return _storage_instance


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = create_storage()
    return _storage_instance


def reset_storage() -> None:
    global _storage_instance
    _storage_instance = None
