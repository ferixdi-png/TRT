import os
from datetime import datetime, timedelta, timezone

import pytest

from app.services import free_tools_service
from app.storage.factory import reset_storage


@pytest.fixture(autouse=True)
def _storage_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "json")
    monkeypatch.setenv("STORAGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TEST_MODE", "1")
    reset_storage()
    yield
    reset_storage()


@pytest.mark.asyncio
async def test_hourly_limit_resets(monkeypatch):
    free_ids = free_tools_service.get_free_tools_model_ids()
    sku_id = free_ids[0]
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(free_tools_service, "_now", lambda: base_time)
    for _ in range(5):
        result = await free_tools_service.check_and_consume_free_generation(123, sku_id)
        assert result["status"] == "ok"

    denied = await free_tools_service.check_and_consume_free_generation(123, sku_id)
    assert denied["status"] == "deny"

    monkeypatch.setattr(free_tools_service, "_now", lambda: base_time + timedelta(hours=1, seconds=1))
    result = await free_tools_service.check_and_consume_free_generation(123, sku_id)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_referral_bonus_adds_capacity(monkeypatch):
    free_ids = free_tools_service.get_free_tools_model_ids()
    sku_id = free_ids[0]
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(free_tools_service, "_now", lambda: base_time)

    await free_tools_service.add_referral_free_bonus(456, 10)

    for _ in range(5):
        result = await free_tools_service.check_and_consume_free_generation(456, sku_id)
        assert result["status"] == "ok"

    referral_use = await free_tools_service.check_and_consume_free_generation(456, sku_id)
    assert referral_use["status"] == "ok"
    assert referral_use["source"] == "referral"
