import pytest

from app.admin.diagnostics import build_admin_diagnostics_report
from app.config_env import validate_config
from app.storage.postgres_storage import PostgresStorage
from bot_kie import get_payment_details, get_support_contact


def _set_partner_env(monkeypatch, overrides=None):
    values = {
        "ADMIN_ID": "123",
        "BOT_INSTANCE_ID": "partner-01",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEF",
        "WEBHOOK_BASE_URL": "https://example.onrender.com",
    }
    if overrides:
        values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_env_validation_required_vars(monkeypatch):
    for key in ("ADMIN_ID", "BOT_INSTANCE_ID", "TELEGRAM_BOT_TOKEN", "WEBHOOK_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    result = validate_config(strict=False)
    assert set(result.missing_required) == {
        "ADMIN_ID",
        "BOT_INSTANCE_ID",
        "TELEGRAM_BOT_TOKEN",
        "WEBHOOK_BASE_URL",
    }


@pytest.mark.asyncio
async def test_tenant_isolation_by_bot_instance_id(monkeypatch):
    storage_alpha = PostgresStorage("postgres://example", partner_id="alpha")
    storage_beta = PostgresStorage("postgres://example", partner_id="beta")

    class FakeConnection:
        def __init__(self):
            self.executed = []

        async def execute(self, query, *args):
            self.executed.append((query, args))

    class FakeAcquire:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def __init__(self, conn):
            self.conn = conn

        def acquire(self):
            return FakeAcquire(self.conn)

    conn_a = FakeConnection()
    conn_b = FakeConnection()

    async def get_pool_a():
        return FakePool(conn_a)

    async def get_pool_b():
        return FakePool(conn_b)

    storage_alpha._get_pool = get_pool_a
    storage_beta._get_pool = get_pool_b

    await storage_alpha._save_json_unlocked("user_balances.json", {"1": 5})
    await storage_beta._save_json_unlocked("user_balances.json", {"1": 7})

    assert conn_a.executed[0][1][0] == "alpha"
    assert conn_b.executed[0][1][0] == "beta"
    assert conn_a.executed[0][1][1] == "user_balances.json"
    assert conn_b.executed[0][1][1] == "user_balances.json"


@pytest.mark.asyncio
async def test_admin_diagnostics_output_contains_keys(monkeypatch):
    _set_partner_env(monkeypatch)

    class FakeStorage:
        async def ping(self):
            return True

        def test_connection(self):
            return True

    monkeypatch.setenv("BOT_MODE", "webhook")

    import app.admin.diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "get_storage", lambda: FakeStorage())

    report = await build_admin_diagnostics_report()
    assert "BOT_INSTANCE_ID" in report
    assert "Tenant scope" in report
    assert "WEBHOOK_BASE_URL" in report
    assert "DB:" in report
    assert "Redis:" in report
    assert "ENV:" in report


def test_payments_support_fallbacks(monkeypatch):
    _set_partner_env(monkeypatch)
    monkeypatch.delenv("PAYMENT_PHONE", raising=False)
    monkeypatch.delenv("PAYMENT_BANK", raising=False)
    monkeypatch.delenv("PAYMENT_CARD_HOLDER", raising=False)
    monkeypatch.delenv("SUPPORT_TELEGRAM", raising=False)
    monkeypatch.delenv("SUPPORT_TEXT", raising=False)

    monkeypatch.setenv("OWNER_PAYMENT_PHONE", "+79990001122")
    monkeypatch.setenv("OWNER_PAYMENT_BANK", "Owner Bank")
    monkeypatch.setenv("OWNER_PAYMENT_CARD_HOLDER", "Owner Name")
    monkeypatch.setenv("OWNER_SUPPORT_TELEGRAM", "@owner_support")
    monkeypatch.setenv("OWNER_SUPPORT_TEXT", "Owner support text")

    payment_details = get_payment_details()
    support_details = get_support_contact()
    assert "+79990001122" in payment_details
    assert "Owner Bank" in payment_details
    assert "Owner Name" in payment_details
    assert "@owner_support" in support_details
    assert "Owner support text" in support_details

    monkeypatch.setenv("PAYMENT_PHONE", "+70000000000")
    monkeypatch.setenv("PAYMENT_BANK", "Partner Bank")
    monkeypatch.setenv("PAYMENT_CARD_HOLDER", "Partner Name")
    monkeypatch.setenv("SUPPORT_TELEGRAM", "@partner_support")
    monkeypatch.setenv("SUPPORT_TEXT", "Partner support text")

    payment_details = get_payment_details()
    support_details = get_support_contact()
    assert "+70000000000" in payment_details
    assert "Partner Bank" in payment_details
    assert "Partner Name" in payment_details
    assert "@partner_support" in support_details
    assert "Partner support text" in support_details
