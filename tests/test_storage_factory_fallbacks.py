from pathlib import Path

from app.storage.factory import create_storage, reset_storage
from app.storage.json_storage import JsonStorage
from app.storage.postgres_storage import PostgresStorage


def _unset_optional(monkeypatch, *keys: str) -> None:
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_storage_factory_db_mode_ignores_github(monkeypatch):
    monkeypatch.setenv("STORAGE_MODE", "db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-db")
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    reset_storage()

    storage = create_storage()

    assert isinstance(storage, PostgresStorage)


def test_storage_factory_fallbacks_to_json_when_db_missing(monkeypatch, tmp_path: Path):
    _unset_optional(
        monkeypatch,
        "DATABASE_URL",
        "STORAGE_MODE",
        "GITHUB_STORAGE_STUB",
        "GITHUB_TOKEN",
        "GITHUB_REPO",
    )
    monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-fallback")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reset_storage()

    storage = create_storage()

    assert isinstance(storage, JsonStorage)
    assert "tenant-fallback" in storage.data_dir.parts
