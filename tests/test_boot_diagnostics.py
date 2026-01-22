import json

import pytest

from app.diagnostics import boot as boot_diagnostics


class FakeStorage:
    def __init__(self):
        self.data = {}
        self.max_pool_size = 5
        self.partner_id = "partner-01"

    async def write_json_file(self, filename, data):
        self.data[filename] = data

    async def read_json_file(self, filename, default=None):
        if filename in self.data:
            return self.data[filename]
        return default or {}

    def _get_file_lock(self):
        return None


class FakeRedis:
    async def ping(self):
        return True

    async def close(self):
        return None


class FakeConn:
    async def fetchval(self, query):
        return 1

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_boot_report_ok_minimal_env(monkeypatch):
    async def fake_connect(_dsn):
        return FakeConn()

    monkeypatch.setattr(boot_diagnostics.asyncpg, "connect", fake_connect)

    config = {
        "ADMIN_ID": "123456",
        "BOT_INSTANCE_ID": "partner-01",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEFabcdef1234567890",
        "WEBHOOK_BASE_URL": "https://example.com",
        "DATABASE_URL": "postgresql://example",
        "BOT_MODE": "polling",
        "PORT": "10000",
        "REDIS_URL": "redis://localhost:6379/0",
        "KIE_API_KEY": "kie-api-key-123456",
        "PAYMENT_BANK": "test",
        "PAYMENT_CARD_HOLDER": "test",
        "PAYMENT_PHONE": "test",
        "SUPPORT_TELEGRAM": "@support",
        "SUPPORT_TEXT": "support",
    }

    report = await boot_diagnostics.run_boot_diagnostics(config, storage=FakeStorage(), redis_client=FakeRedis())

    assert report["result"] == boot_diagnostics.RESULT_READY
    assert report["sections"]["DATABASE"]["status"] == boot_diagnostics.STATUS_OK
    assert report["sections"]["REDIS"]["status"] == boot_diagnostics.STATUS_OK


@pytest.mark.asyncio
async def test_boot_report_fail_missing_required_env(monkeypatch):
    async def fake_connect(_dsn):
        return FakeConn()

    monkeypatch.setattr(boot_diagnostics.asyncpg, "connect", fake_connect)

    config = {
        "DATABASE_URL": "postgresql://example",
    }
    report = await boot_diagnostics.run_boot_diagnostics(config, storage=FakeStorage(), redis_client=None)

    assert report["result"] == boot_diagnostics.RESULT_FAIL
    assert "ADMIN_ID" in report["critical_failures"]
    assert "TELEGRAM_BOT_TOKEN" in report["critical_failures"]


@pytest.mark.asyncio
async def test_boot_report_degraded_no_redis_no_kie(monkeypatch):
    async def fake_connect(_dsn):
        return FakeConn()

    monkeypatch.setattr(boot_diagnostics.asyncpg, "connect", fake_connect)

    config = {
        "ADMIN_ID": "123456",
        "BOT_INSTANCE_ID": "partner-01",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEFabcdef1234567890",
        "WEBHOOK_BASE_URL": "https://example.com",
        "DATABASE_URL": "postgresql://example",
        "BOT_MODE": "polling",
        "PORT": "10000",
    }

    report = await boot_diagnostics.run_boot_diagnostics(config, storage=FakeStorage(), redis_client=None)

    assert report["result"] == boot_diagnostics.RESULT_DEGRADED
    assert report["sections"]["REDIS"]["status"] == boot_diagnostics.STATUS_DEGRADED
    assert report["sections"]["AI"]["status"] == boot_diagnostics.STATUS_DEGRADED


@pytest.mark.asyncio
async def test_no_secrets_in_boot_logs(monkeypatch):
    async def fake_connect(_dsn):
        return FakeConn()

    monkeypatch.setattr(boot_diagnostics.asyncpg, "connect", fake_connect)

    config = {
        "ADMIN_ID": "123456",
        "BOT_INSTANCE_ID": "partner-01",
        "TELEGRAM_BOT_TOKEN": "123456:SECRET_TELEGRAM_TOKEN",
        "WEBHOOK_BASE_URL": "https://example.com",
        "DATABASE_URL": "postgresql://example",
        "BOT_MODE": "polling",
        "PORT": "10000",
        "KIE_API_KEY": "SECRET_KIE_KEY",
    }

    report = await boot_diagnostics.run_boot_diagnostics(config, storage=FakeStorage(), redis_client=None)

    report_json = json.dumps(report, ensure_ascii=False)
    report_text = boot_diagnostics.format_boot_report(report)

    assert "SECRET_TELEGRAM_TOKEN" not in report_json
    assert "SECRET_TELEGRAM_TOKEN" not in report_text
    assert "SECRET_KIE_KEY" not in report_json
    assert "SECRET_KIE_KEY" not in report_text
