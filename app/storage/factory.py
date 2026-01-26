"""Storage factory for PostgreSQL/Hybrid backends."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Set, Awaitable

from app.storage.base import BaseStorage
from app.storage.postgres_storage import PostgresStorage
from app.storage.json_storage import JsonStorage
from app.storage.github_storage import GitHubStorage
from app.storage.hybrid_storage import HybridStorage

logger = logging.getLogger(__name__)

_storage_instance: Optional[BaseStorage] = None
_runtime_migration_task: Optional[asyncio.Task] = None


def _resolve_mode(storage_mode: Optional[str]) -> str:
    if storage_mode:
        return storage_mode.strip().lower()
    return os.getenv("STORAGE_MODE", "").strip().lower()


def _runtime_files() -> Set[str]:
    return {
        "user_balances.json",
        "daily_free_generations.json",
        "hourly_free_usage.json",
        "referral_free_bank.json",
        "admin_limits.json",
    }


def _resolve_tenant_dir(base_dir: Path, bot_instance_id: str) -> Path:
    if bot_instance_id and bot_instance_id not in base_dir.parts:
        return base_dir / bot_instance_id
    return base_dir


async def _migrate_runtime_files(
    primary: BaseStorage,
    runtime: JsonStorage,
    runtime_dir: Path,
) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for filename in _runtime_files():
        try:
            payload = await primary.read_json_file(filename, default={})
            await runtime.write_json_file(filename, payload)
        except Exception as exc:
            logger.warning("[STORAGE] runtime_migration_failed file=%s error=%s", filename, exc)
    marker = runtime_dir / ".runtime_migrated"
    try:
        marker.write_text("ok", encoding="utf-8")
    except Exception as exc:
        logger.warning("[STORAGE] runtime_marker_write_failed error=%s", exc)


def _schedule_runtime_migration(primary: BaseStorage, runtime: JsonStorage, runtime_dir: Path) -> None:
    global _runtime_migration_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _runtime_migration_task = None
        return
    if _runtime_migration_task and not _runtime_migration_task.done():
        return
    _runtime_migration_task = loop.create_task(_migrate_runtime_files(primary, runtime, runtime_dir))


def get_runtime_migration_task() -> Optional[Awaitable[None]]:
    return _runtime_migration_task


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
    explicit_db_mode = mode in {"db", "postgres"}
    database_url = database_url or os.getenv("DATABASE_URL", "").strip() or None
    partner_id = os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or ""

    github_enabled = os.getenv("GITHUB_STORAGE_STUB", "0").lower() in ("1", "true", "yes")
    if os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"):
        github_enabled = True

    if explicit_db_mode and github_enabled:
        logger.info(
            "[STORAGE] github_backend_disabled=true reason=explicit_db_mode mode=%s",
            mode,
        )
    if not explicit_db_mode and (mode in {"github", "github_json", "hybrid"} or github_enabled):
        primary = GitHubStorage()
        runtime_dir = Path(os.getenv("RUNTIME_STORAGE_DIR", data_dir or "./runtime"))
        runtime_dir = _resolve_tenant_dir(runtime_dir, partner_id or "default")
        runtime = JsonStorage(data_dir=str(runtime_dir), bot_instance_id=partner_id or "default")
        storage = HybridStorage(primary, runtime, runtime_files=_runtime_files())
        _storage_instance = storage
        _schedule_runtime_migration(primary, runtime, runtime_dir)
        logger.info(
            "[STORAGE] backend=hybrid runtime_dir=%s partner_id=%s",
            runtime_dir,
            partner_id or "default",
        )
        return storage

    if not database_url:
        if explicit_db_mode:
            if os.getenv("TEST_MODE", "").lower() in ("1", "true", "yes"):
                fallback_dir = Path(os.getenv("DATA_DIR", data_dir or "./data"))
                fallback_partner = partner_id or "default"
                fallback_dir = _resolve_tenant_dir(fallback_dir, fallback_partner)
                _storage_instance = JsonStorage(data_dir=str(fallback_dir), bot_instance_id=fallback_partner)
                logger.warning(
                    "[STORAGE] backend=json reason=missing_database_url_test_mode partner_id=%s data_dir=%s",
                    fallback_partner,
                    fallback_dir,
                )
                return _storage_instance
            raise RuntimeError("DATABASE_URL is required for PostgreSQL storage")
        fallback_dir = Path(os.getenv("DATA_DIR", data_dir or "./data"))
        fallback_partner = partner_id or "default"
        fallback_dir = _resolve_tenant_dir(fallback_dir, fallback_partner)
        _storage_instance = JsonStorage(data_dir=str(fallback_dir), bot_instance_id=fallback_partner)
        logger.warning(
            "[STORAGE] backend=json reason=missing_database_url partner_id=%s data_dir=%s",
            fallback_partner,
            fallback_dir,
        )
        return _storage_instance
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
    global _storage_instance, _runtime_migration_task
    _storage_instance = None
    _runtime_migration_task = None
