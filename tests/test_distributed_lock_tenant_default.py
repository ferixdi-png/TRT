from app.utils.distributed_lock import build_tenant_lock_key


def test_distributed_lock_defaults_to_tenant_default(monkeypatch):
    monkeypatch.delenv("BOT_INSTANCE_ID", raising=False)
    monkeypatch.delenv("PARTNER_ID", raising=False)

    assert build_tenant_lock_key("free:123") == "tenant:default:free:123"
