import json

import pytest

from app.storage.json_storage import JsonStorage


@pytest.mark.asyncio
async def test_json_storage_loads_nested_json_string(tmp_path) -> None:
    storage = JsonStorage(data_dir=str(tmp_path), bot_instance_id="test-instance")
    target = storage.data_dir / "user_registry.json"
    target.write_text(json.dumps({"user": 1}), encoding="utf-8")
    nested = json.dumps(target.read_text(encoding="utf-8"))
    target.write_text(nested, encoding="utf-8")

    payload = await storage._load_json(target)

    assert payload == {"user": 1}


@pytest.mark.asyncio
async def test_json_storage_rejects_non_object_json(tmp_path) -> None:
    storage = JsonStorage(data_dir=str(tmp_path), bot_instance_id="test-instance")
    target = storage.data_dir / "user_registry.json"
    target.write_text(json.dumps("oops"), encoding="utf-8")

    payload = await storage._load_json(target)

    assert payload == {}
