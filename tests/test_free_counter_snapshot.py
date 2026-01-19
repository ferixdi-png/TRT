from datetime import datetime, timezone, timedelta

import pytest

from app.services import free_tools_service
from app.storage.json_storage import JsonStorage


@pytest.mark.asyncio
async def test_free_counter_snapshot_window(monkeypatch, tmp_path):
    storage = JsonStorage(data_dir=tmp_path)
    user_id = 123
    window_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await storage.set_hourly_free_usage(user_id, window_start.isoformat(), 3)
    monkeypatch.setattr(free_tools_service, "get_storage", lambda: storage)

    snapshot = await free_tools_service.get_free_counter_snapshot(
        user_id, now=window_start + timedelta(minutes=10)
    )

    assert snapshot["used_in_current_window"] == 3
    assert snapshot["remaining"] == max(0, snapshot["limit_per_hour"] - 3)
    assert snapshot["next_refill_in"] == 50 * 60


@pytest.mark.asyncio
async def test_free_counter_snapshot_resets_after_hour(monkeypatch, tmp_path):
    storage = JsonStorage(data_dir=tmp_path)
    user_id = 456
    window_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await storage.set_hourly_free_usage(user_id, window_start.isoformat(), 5)
    monkeypatch.setattr(free_tools_service, "get_storage", lambda: storage)

    snapshot = await free_tools_service.get_free_counter_snapshot(
        user_id, now=window_start + timedelta(hours=1, minutes=1)
    )

    assert snapshot["used_in_current_window"] == 0
    assert snapshot["remaining"] == snapshot["limit_per_hour"]
    assert snapshot["next_refill_in"] == 3600
