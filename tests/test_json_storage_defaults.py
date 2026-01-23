from pathlib import Path

from app.storage.json_storage import JsonStorage


def test_json_storage_defaults_to_tenant(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("BOT_INSTANCE_ID", raising=False)

    storage = JsonStorage(data_dir=str(tmp_path))

    assert storage.bot_instance_id == "default"
    assert "default" in storage.data_dir.parts
