import json
from datetime import datetime

import pytest

from app.config_env import validate_config
from app.storage.github_storage import GitHubStorage, GitHubConflictError
from app.storage.json_storage import JsonStorage
from app.services.history_service import append_event, get_recent


def _set_required_env(monkeypatch, overrides=None):
    values = {
        "ADMIN_ID": "123",
        "BOT_INSTANCE_ID": "partner-instance",
        "BOT_MODE": "webhook",
        "GITHUB_BRANCH": "main",
        "GITHUB_COMMITTER_EMAIL": "bot@example.com",
        "GITHUB_COMMITTER_NAME": "Partner Bot",
        "GITHUB_REPO": "owner/repo",
        "GITHUB_TOKEN": "ghp_1234567890abcdef",
        "KIE_API_KEY": "kie_1234567890abcdef",
        "PAYMENT_BANK": "Test Bank",
        "PAYMENT_CARD_HOLDER": "Test Holder",
        "PAYMENT_PHONE": "+1234567890",
        "PORT": "8080",
        "STORAGE_MODE": "github",
        "STORAGE_PREFIX": "storage",
        "SUPPORT_TELEGRAM": "@supportuser",
        "SUPPORT_TEXT": "Support text",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEF",
        "WEBHOOK_BASE_URL": "https://example.com",
    }
    if overrides:
        values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


class BranchCaptureStorage(GitHubStorage):
    def __init__(self):
        super().__init__()
        self.captured_payload = None
        self._storage_branch_checked = True

    async def _request_with_retry(self, method, url, *, op, path, ok_statuses, **kwargs):
        if op == "write":
            self.captured_payload = kwargs.get("json")
            return self._ResponsePayload(status=201, headers={}, text=json.dumps({"sha": "test"}))
        return self._ResponsePayload(status=200, headers={}, text=json.dumps({}))


class ConflictStorage(GitHubStorage):
    def __init__(self):
        super().__init__()
        self._conflict_once = True
        self._storage_branch_checked = True

    async def _write_json(self, filename, data, sha):
        if self._conflict_once:
            self._conflict_once = False
            path = self._storage_path(filename)
            if filename == self.balances_file:
                self._stub_store[path] = ({"1": 5.0}, "sha-other")
            if filename == self.free_generations_file:
                today = datetime.now().strftime("%Y-%m-%d")
                self._stub_store[path] = ({"1": {"date": today, "count": 1, "bonus": 0}}, "sha-other")
            raise GitHubConflictError("conflict")
        return await super()._write_json(filename, data, sha)


@pytest.mark.asyncio
async def test_storage_branch_only(monkeypatch):
    _set_required_env(monkeypatch, {"STORAGE_BRANCH": "storage"})
    validate_config(strict=True)

    storage = BranchCaptureStorage()

    await storage.write_json_file("user_balances.json", {"1": 10.0})
    assert storage.captured_payload is not None
    assert storage.captured_payload["branch"] == "storage"
    assert storage.captured_payload["branch"] != storage.config.code_branch


@pytest.mark.asyncio
async def test_history_idempotent(tmp_path, monkeypatch):
    _set_required_env(monkeypatch, {"DATA_DIR": str(tmp_path), "STORAGE_MODE": "github"})
    storage = JsonStorage(data_dir=str(tmp_path), bot_instance_id="test-instance")

    event_id = "evt-123"
    await append_event(storage, user_id=1, kind="generation", payload={"x": 1}, event_id=event_id)
    await append_event(storage, user_id=1, kind="generation", payload={"x": 1}, event_id=event_id)

    recent = await get_recent(storage, user_id=1, limit=10)
    assert len(recent) == 1
    assert recent[0]["event_id"] == event_id


@pytest.mark.asyncio
async def test_concurrent_merge(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")

    storage = ConflictStorage()

    await storage.add_user_balance(1, 10.0)
    balance_data = storage._stub_store[storage._storage_path(storage.balances_file)][0]
    assert balance_data["1"] == 15.0

    storage._conflict_once = True
    await storage.increment_free_generations(1)
    free_data = storage._stub_store[storage._storage_path(storage.free_generations_file)][0]
    assert free_data["1"]["count"] == 2
