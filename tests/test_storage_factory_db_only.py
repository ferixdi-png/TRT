import logging

import pytest

from app.storage.factory import create_storage, reset_storage
from app.storage.postgres_storage import PostgresStorage


@pytest.mark.parametrize("mode", [None, "db", "github", "github_json", "postgres"])
def test_factory_forces_postgres(mode, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("BOT_INSTANCE_ID", "test-instance")
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    reset_storage()
    caplog.set_level(logging.INFO)
    storage = create_storage(storage_mode=mode)

    assert isinstance(storage, PostgresStorage)
    assert "[STORAGE][GITHUB]" not in caplog.text
    assert "missing_required_envs" not in caplog.text
