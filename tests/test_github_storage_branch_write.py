import json

import pytest

from app.storage.github_storage import GitHubStorage


@pytest.mark.asyncio
async def test_storage_writes_use_storage_branch(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.setenv("STORAGE_GITHUB_BRANCH", "storage")

    storage = GitHubStorage()

    async def noop_branch_check():
        return None

    monkeypatch.setattr(storage, "_ensure_storage_branch_exists", noop_branch_check)

    captured_payloads = []

    async def fake_request_with_retry(method, url, *, op, path, ok_statuses, **kwargs):
        if method == "PUT":
            captured_payloads.append(kwargs.get("json"))
        return storage._ResponsePayload(
            status=200,
            headers={},
            text=json.dumps({"content": {"sha": "sha123"}}),
        )

    monkeypatch.setattr(storage, "_request_with_retry", fake_request_with_retry)

    await storage._write_json(storage.balances_file, {"1": 10.0}, None)
    await storage._write_json(storage.free_generations_file, {"1": {"count": 1}}, None)
    await storage._write_json(storage.admin_limits_file, {"1": {"limit": 100}}, None)

    assert captured_payloads, "Expected write payloads to be captured"
    for payload in captured_payloads:
        assert payload["branch"] == "storage"
        assert payload["branch"] != "main"
