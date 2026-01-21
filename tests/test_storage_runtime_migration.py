import asyncio
from pathlib import Path

import pytest

from app.storage.factory import get_storage, reset_storage, get_runtime_migration_task
from app.storage.hybrid_storage import HybridStorage


@pytest.mark.asyncio
async def test_runtime_migration_scheduled_when_loop_running(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "stub-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-01")
    monkeypatch.setenv("STORAGE_BRANCH", "storage")
    monkeypatch.setenv("GITHUB_BRANCH", "main")
    monkeypatch.setenv("RUNTIME_STORAGE_DIR", str(tmp_path / "runtime"))

    reset_storage()
    storage = get_storage()
    assert isinstance(storage, HybridStorage)

    task = get_runtime_migration_task()
    if task is not None:
        await asyncio.wait_for(task, timeout=2)

    marker_path = Path(tmp_path / "runtime" / ".runtime_migrated")
    for _ in range(20):
        if marker_path.exists():
            break
        await asyncio.sleep(0.05)

    assert marker_path.exists()
