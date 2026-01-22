"""Storage factory for GitHub or PostgreSQL backends."""

import logging
import os
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.github_storage import GitHubStorage
from app.storage.postgres_storage import PostgresStorage

logger = logging.getLogger(__name__)

_storage_instance: Optional[BaseStorage] = None


def _resolve_mode(explicit_mode: Optional[str]) -> str:
    mode = (explicit_mode or os.getenv("STORAGE_MODE", "auto")).strip().lower()
    if mode not in {"auto", "github", "postgres"}:
        logger.warning("[STORAGE] unknown mode=%s, falling back to auto", mode)
        mode = "auto"
    if mode == "auto":
        return "postgres" if os.getenv("DATABASE_URL") else "github"
    return mode


def create_storage(
    storage_mode: Optional[str] = None,
    database_url: Optional[str] = None,
    data_dir: Optional[str] = None,
) -> BaseStorage:
    """Create storage instance based on env."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    mode = _resolve_mode(storage_mode)
    database_url = database_url or os.getenv("DATABASE_URL", "").strip() or None

    if mode == "postgres":
        if not database_url:
            raise RuntimeError("STORAGE_MODE=postgres but DATABASE_URL is missing")
        partner_id = os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or "partner-01"
        storage = PostgresStorage(database_url, partner_id=partner_id)

        async def _maybe_migrate() -> None:
            try:
                empty = await storage.is_empty()
                if not empty:
                    return
                github_storage = GitHubStorage()
                await storage.migrate_from_github(github_storage)
            except Exception as exc:
                logger.warning("[STORAGE] migration skipped error=%s", exc)

        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_maybe_migrate())
            else:
                loop.run_until_complete(_maybe_migrate())
        except Exception:
            pass

        _storage_instance = storage
        logger.info("[STORAGE] backend=postgres partner_id=%s", partner_id)
        return _storage_instance

    _storage_instance = GitHubStorage()
    logger.info("[STORAGE] backend=github")
    return _storage_instance


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = create_storage()
    return _storage_instance


def reset_storage() -> None:
    global _storage_instance
    _storage_instance = None
