"""
Storage factory - выбор storage (GitHub with test fallback).
В продакшене используется GitHub Contents API, в тестах возможен JSON fallback.
"""

import logging
import os
import asyncio
from typing import Optional

from app.storage.base import BaseStorage
from app.storage.github_storage import GitHubStorage
from app.storage.json_storage import JsonStorage
from app.storage.hybrid_storage import HybridStorage

logger = logging.getLogger(__name__)

# Глобальный экземпляр storage (singleton)
_storage_instance: Optional[BaseStorage] = None
_storage_mode_logged = False
_runtime_migration_task: Optional[asyncio.Task] = None


def create_storage(
    storage_mode: Optional[str] = None,
    database_url: Optional[str] = None,
    data_dir: Optional[str] = None
) -> BaseStorage:
    """
    Создает storage instance
    
    Args:
        storage_mode: 'github' (default) или 'auto' (для github)
        database_url: игнорируется (БД отключены)
        data_dir: игнорируется (БД отключены)
    
    Returns:
        BaseStorage instance
    """
    global _storage_instance
    global _storage_mode_logged
    
    if _storage_instance is not None:
        return _storage_instance
    
    # Определяем режим
    if storage_mode is None:
        storage_mode = os.getenv('STORAGE_MODE', '').lower()
    storage_mode = storage_mode.lower()

    github_only = os.getenv("GITHUB_ONLY_STORAGE", "true").lower() in ("1", "true", "yes")
    if not github_only:
        logger.warning("[STORAGE] enforcing_github_only=true reason=GITHUB_ONLY_STORAGE_default")

    test_mode = os.getenv("TEST_MODE", "0") == "1"
    dry_run = os.getenv("DRY_RUN", "0") == "1"

    if storage_mode in {"json", "local", "file"}:
        storage_path = data_dir or os.getenv("STORAGE_DATA_DIR", "./data")
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=github_only path=%s",
            storage_mode,
            storage_path,
        )

    if storage_mode not in {"", "github", "github_json"}:
        logger.warning(
            "[STORAGE] mode_override=true requested=%s using=github reason=github_only",
            storage_mode,
        )

    if not _storage_mode_logged:
        logger.info("STORAGE_MODE=GITHUB_JSON (DB_DISABLED=true)")
        _storage_mode_logged = True

    try:
        github_storage = GitHubStorage()
    except ValueError:
        if test_mode or dry_run:
            logger.error("[STORAGE] github_init_failed mode=github_json env_missing=true")
        raise

    runtime_mode = os.getenv("RUNTIME_STORAGE_MODE", "auto").lower()
    runtime_dir = data_dir or os.getenv("RUNTIME_STORAGE_DIR", "/tmp/trt-runtime")
    runtime_files = {
        "user_balances.json",
        "daily_free_generations.json",
        "admin_limits.json",
        "hourly_free_usage.json",
        "referral_free_bank.json",
    }

    if runtime_mode in {"off", "disabled", "github"}:
        _storage_instance = github_storage
        logger.info(
            "[PERSISTENCE] storage_mode=GITHUB_JSON repo=%s branch=%s prefix=%s runtime_files=%s "
            "runtime_dir=%s runtime_cache_only=true PERSISTENCE_OK=true balances_and_free_limits_persist_in=github",
            github_storage.config.storage_repo,
            github_storage.config.storage_branch,
            github_storage.config.storage_prefix,
            ",".join(sorted(runtime_files)),
            runtime_dir,
        )
        return _storage_instance

    if runtime_mode in {"postgres", "pg", "auto"} and os.getenv("DATABASE_URL"):
        logger.warning(
            "[STORAGE] runtime_db_unavailable=true using=json_runtime reason=missing_db_driver",
        )

    runtime_storage = JsonStorage(runtime_dir)

    marker_path = os.path.join(runtime_dir, ".runtime_migrated")
    async def _migrate_runtime() -> None:
        migrated = []
        for filename in runtime_files:
            try:
                payload = await github_storage.read_json_file(filename, default={})
            except Exception as exc:
                logger.warning("[STORAGE] runtime_migration_read_failed path=%s error=%s", filename, exc)
                continue
            if payload:
                try:
                    await runtime_storage.write_json_file(filename, payload)
                    migrated.append(filename)
                except Exception as exc:
                    logger.warning("[STORAGE] runtime_migration_write_failed path=%s error=%s", filename, exc)
        try:
            os.makedirs(runtime_dir, exist_ok=True)
            with open(marker_path, "w", encoding="utf-8") as marker_file:
                marker_file.write("ok")
            logger.info(
                "[STORAGE] runtime_migration_completed migrated_files=%s",
                ",".join(sorted(migrated)) if migrated else "none",
            )
        except Exception as exc:
            logger.warning("[STORAGE] runtime_migration_marker_failed error=%s", exc)

    def _schedule_migration(loop: asyncio.AbstractEventLoop) -> None:
        global _runtime_migration_task
        if _runtime_migration_task and not _runtime_migration_task.done():
            return
        _runtime_migration_task = loop.create_task(_migrate_runtime())

        def _done_callback(task: asyncio.Task) -> None:
            try:
                task.result()
            except Exception as exc:
                logger.warning("[STORAGE] runtime_migration_failed error=%s", exc)

        _runtime_migration_task.add_done_callback(_done_callback)
        logger.info("[STORAGE] runtime_migration_scheduled=true")

    if not os.path.exists(marker_path):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            _schedule_migration(loop)
        else:
            asyncio.run(_migrate_runtime())

    _storage_instance = HybridStorage(github_storage, runtime_storage, runtime_files=runtime_files)
    logger.info(
        "[STORAGE] runtime_override=true mode=hybrid runtime_dir=%s runtime_files=%s",
        runtime_dir,
        ",".join(sorted(runtime_files)),
    )
    logger.info(
        "[PERSISTENCE] storage_mode=GITHUB_JSON repo=%s branch=%s prefix=%s runtime_files=%s "
        "runtime_dir=%s runtime_cache_only=true PERSISTENCE_OK=true balances_and_free_limits_persist_in=github",
        github_storage.config.storage_repo,
        github_storage.config.storage_branch,
        github_storage.config.storage_prefix,
        ",".join(sorted(runtime_files)),
        runtime_dir,
    )
    return _storage_instance


def get_storage() -> BaseStorage:
    """
    Получить текущий storage instance (singleton)
    
    Returns:
        BaseStorage instance
    """
    global _storage_instance
    
    if _storage_instance is None:
        _storage_instance = create_storage()
    
    return _storage_instance


def reset_storage() -> None:
    """Сбросить storage instance (для тестов)"""
    global _storage_instance
    _storage_instance = None


def get_runtime_migration_task() -> Optional[asyncio.Task]:
    """Expose last scheduled runtime migration task for tests."""
    return _runtime_migration_task
