from app.admin.auth import get_admin_ids, is_admin, reset_admin_ids_cache
from app.config_env import validate_config
from app.storage.json_storage import JsonStorage
from app.utils.distributed_lock import build_redis_lock_key


def _set_required_env(monkeypatch, overrides=None):
    values = {
        "ADMIN_ID": "123",
        "BOT_INSTANCE_ID": "partner-01",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEF",
        "WEBHOOK_BASE_URL": "https://example.com",
    }
    if overrides:
        values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_env_validation_rejects_invalid_instance_id(monkeypatch):
    _set_required_env(monkeypatch, {"BOT_INSTANCE_ID": "Bad/Slug"})
    result = validate_config(strict=False)
    assert any("BOT_INSTANCE_ID" in item for item in result.invalid_required)


def test_is_admin_parses_admin_id_list(monkeypatch):
    monkeypatch.setenv("ADMIN_ID", "123, 456 789")
    reset_admin_ids_cache()
    ids = get_admin_ids()
    assert ids == {123, 456, 789}
    assert is_admin(123) is True
    assert is_admin(999) is False


def test_json_storage_scopes_data_dir(tmp_path):
    storage = JsonStorage(data_dir=str(tmp_path), bot_instance_id="tenant-alpha")
    assert "tenant-alpha" in storage.data_dir.parts


def test_redis_lock_key_scoped_by_tenant(monkeypatch):
    monkeypatch.setenv("BOT_INSTANCE_ID", "tenant-alpha")
    assert build_redis_lock_key("balance:1") == "lock:tenant:tenant-alpha:balance:1"
