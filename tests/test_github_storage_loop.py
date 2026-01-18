import asyncio

from app.storage.github_storage import GitHubStorage


class DummySession:
    def __init__(self):
        self.closed = False
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        self.closed = True


def test_github_storage_loop_mismatch_does_not_close(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")

    created_sessions = []

    def dummy_client_session(*args, **kwargs):
        session = DummySession()
        created_sessions.append(session)
        return session

    monkeypatch.setattr(
        "app.storage.github_storage.aiohttp.ClientSession",
        dummy_client_session,
    )

    storage = GitHubStorage()

    loop1 = asyncio.new_event_loop()
    session1 = loop1.run_until_complete(storage._get_session())
    loop1.close()

    loop2 = asyncio.new_event_loop()
    session2 = loop2.run_until_complete(storage._get_session())
    loop2.close()

    assert session1 is created_sessions[0]
    assert session2 is created_sessions[1]
    assert session1.close_calls == 0
    assert session1.closed is False
