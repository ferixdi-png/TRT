import base64
import json
from typing import Optional

import pytest

from app.storage.github_storage import GitHubStorage


class DummyResponse:
    def __init__(self, status: int, payload: Optional[dict] = None):
        self.status = status
        self._payload = payload or {}
        self.headers = {}
        self.released = False

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    async def release(self):
        self.released = True


class DummySession:
    def __init__(self):
        self.closed = False
        self.close_calls = 0

    async def request(self, method: str, url: str, **kwargs):
        if method == "GET":
            encoded = base64.b64encode(b"{}").decode("utf-8")
            return DummyResponse(200, {"content": encoded, "sha": "abc123"})
        return DummyResponse(200, {})

    async def close(self):
        self.close_calls += 1
        self.closed = True


@pytest.mark.asyncio
async def test_github_storage_smoke_closes_session(monkeypatch, caplog, request=None):
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")

    created_sessions: list[DummySession] = []

    def dummy_client_session(*args, **kwargs):
        session = DummySession()
        created_sessions.append(session)
        return session

    monkeypatch.setattr(
        "app.storage.github_storage.aiohttp.ClientSession",
        dummy_client_session,
    )

    storage = GitHubStorage()

    for _ in range(25):
        await storage.add_user_balance(123, 1.0)
        await storage.get_user_balance(123)

    await storage.close()

    assert created_sessions, "Expected at least one session to be created"
    assert created_sessions[0].closed is True
    assert created_sessions[0].close_calls == 1
    warning_messages = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert not any("session_detached" in message for message in warning_messages)
