from unittest.mock import MagicMock

import pytest

from bot_kie import save_json_file
from app.storage.factory import get_storage, reset_storage


@pytest.mark.asyncio
async def test_save_json_file_sanitizes_non_serializable(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-sanitize")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STORAGE_MODE", raising=False)
    reset_storage()

    save_json_file("user_registry.json", {"1": {"user": MagicMock(name="user")}})

    storage = get_storage()
    payload = await storage.read_json_file("user_registry.json", default={})
    assert isinstance(payload["1"]["user"], str)
