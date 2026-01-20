from datetime import datetime

import pytest

from app.services import free_tools_service
from app.storage.factory import reset_storage


@pytest.fixture(autouse=True)
def _storage_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "github_json")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("TEST_MODE", "1")
    reset_storage()
    yield
    reset_storage()


@pytest.mark.asyncio
async def test_daily_limit_enforced(monkeypatch):
    free_ids = free_tools_service.get_free_tools_model_ids()
    sku_id = free_ids[0]
    base_time = datetime(2025, 1, 1)

    monkeypatch.setattr(free_tools_service, "_now", lambda: base_time)
    for _ in range(5):
        result = await free_tools_service.check_and_consume_free_generation(123, sku_id)
        assert result["status"] == "ok"

    denied = await free_tools_service.check_and_consume_free_generation(123, sku_id)
    assert denied["status"] == "deny"
