import asyncio

import pytest

from app.storage.github_storage import GitHubStorage
from app.storage.hybrid_storage import HybridStorage


class LoopErrorStorage(GitHubStorage):
    def __init__(self):
        super().__init__()
        self.calls = 0
        self.reset_reasons = []

    async def _reset_session_for_loop(self, reason: str) -> None:
        self.reset_reasons.append(reason)

    async def _request_raw(self, method: str, url: str, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Task got Future attached to a different loop")
        return self._ResponsePayload(status=200, headers={}, text="{}")


@pytest.mark.asyncio
async def test_github_storage_resets_on_loop_error(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("GITHUB_BACKOFF_BASE", "0")

    storage = LoopErrorStorage()
    response = await storage._request_with_retry(
        "GET",
        "https://example.com",
        op="test",
        path="loop",
        ok_statuses=(200,),
    )

    assert response.status == 200
    assert storage.calls == 2
    assert storage.reset_reasons


class DummyRuntimeStorage:
    async def read_json_file(self, filename: str, default=None):
        return default or {}

    async def write_json_file(self, filename: str, data):
        return None

    async def update_json_file(self, filename: str, update_fn):
        return update_fn({})


class FlakyPrimaryStorage:
    def __init__(self):
        self.calls = 0

    async def read_json_file(self, filename: str, default=None):
        self.calls += 1
        if self.calls == 1:
            return {"ok": True}
        raise RuntimeError("boom")

    async def write_json_file(self, filename: str, data):
        return None

    async def update_json_file(self, filename: str, update_fn):
        return update_fn({})


@pytest.mark.asyncio
async def test_hybrid_storage_fallback_returns_last_known_good():
    hybrid = HybridStorage(FlakyPrimaryStorage(), DummyRuntimeStorage())
    first = await hybrid.read_json_file("referrals.json", default={"default": True})
    assert first == {"ok": True}

    second = await hybrid.read_json_file("referrals.json", default={"default": True})
    assert second == {"ok": True}


class CountingStorage(GitHubStorage):
    def __init__(self):
        super().__init__()
        self.fetch_calls = 0

    async def _ensure_storage_branch_exists(self) -> None:
        return None

    async def _fetch_json_payload(self, filename: str):
        self.fetch_calls += 1
        await asyncio.sleep(0.01)
        return {"value": 1}, "sha", 200


@pytest.mark.asyncio
async def test_github_storage_singleflight_reads(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("GITHUB_BACKOFF_BASE", "0")

    storage = CountingStorage()
    results = await asyncio.gather(
        *[storage.read_json_file("referrals.json") for _ in range(20)]
    )

    assert all(result == {"value": 1} for result in results)
    assert storage.fetch_calls == 1
