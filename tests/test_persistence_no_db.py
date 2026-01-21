import pytest

from app.storage.factory import get_storage, reset_storage
from app.storage.hybrid_storage import HybridStorage


@pytest.mark.asyncio
async def test_runtime_write_through_persists_to_github_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "stub-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-01")
    monkeypatch.setenv("STORAGE_BRANCH", "storage")
    monkeypatch.setenv("GITHUB_BRANCH", "main")
    monkeypatch.setenv("RUNTIME_STORAGE_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("HYBRID_RUNTIME_WRITE_THROUGH", "1")
    monkeypatch.setenv("HYBRID_BALANCE_WRITE_THROUGH", "1")

    reset_storage()
    storage = get_storage()
    assert isinstance(storage, HybridStorage)

    await storage.add_user_balance(123, 10.0)
    balances = await storage._primary.read_json_file("user_balances.json", default={})
    assert balances.get("123") == 10.0

    await storage.increment_free_generations(123)
    free_daily = await storage._primary.read_json_file("daily_free_generations.json", default={})
    assert free_daily.get("123", {}).get("count") == 1
