from __future__ import annotations

import pytest

from app.bootstrap import DependencyContainer


class DummySettings:
    kie_api_key = ""


class DummyStorage:
    def __init__(self) -> None:
        self.ping_called = False

    async def ping(self) -> bool:
        self.ping_called = True
        return True

    def test_connection(self) -> bool:
        raise AssertionError("test_connection should not be called when ping is available")


@pytest.mark.asyncio
async def test_dependency_container_prefers_ping(monkeypatch) -> None:
    dummy_storage = DummyStorage()

    monkeypatch.setattr("app.bootstrap.get_storage", lambda: dummy_storage)

    deps = DependencyContainer()
    await deps.initialize(DummySettings())

    assert dummy_storage.ping_called is True
