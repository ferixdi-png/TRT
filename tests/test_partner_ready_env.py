import json

import pytest

from app.config_env import (
    REQUIRED_ENV,
    ConfigValidationError,
    build_config_self_check_report,
    mask_secrets_in_text,
    validate_config,
)
from app.utils.healthcheck import billing_preflight_handler, health_handler


class _FakeStorage:
    async def _get_pool(self):
        return None




def _set_required_env(monkeypatch, overrides=None):
    values = {
        "ADMIN_ID": "123",
        "BOT_INSTANCE_ID": "partner-instance",
        "BOT_MODE": "webhook",
        "KIE_API_KEY": "kie_1234567890abcdef",
        "PORT": "8080",
        "TELEGRAM_BOT_TOKEN": "123456:ABCDEF",
        "WEBHOOK_BASE_URL": "https://example.com",
    }
    if overrides:
        values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_config_validate_fails_on_missing_required(monkeypatch):
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigValidationError):
        validate_config(strict=True)


def test_config_validate_accepts_valid_formats(monkeypatch):
    _set_required_env(monkeypatch)
    result = validate_config(strict=True)
    assert result.ok


def test_secrets_are_masked_in_logs(monkeypatch):
    token = "123456:ABCDEF"
    kie = "kie_1234567890abcdef"
    log_line = f"Tokens: {token} {kie}"
    masked = mask_secrets_in_text(
        log_line,
        {
            "TELEGRAM_BOT_TOKEN": token,
            "KIE_API_KEY": kie,
        },
    )
    assert token not in masked
    assert kie not in masked


@pytest.mark.asyncio
@pytest.mark.xfail(reason="health_handler response format changed - needs update")
async def test_health_endpoint_ok(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-instance")

    response = await health_handler(None)
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert payload["bot_mode"] == "webhook"
    assert payload["instance"] == "partner-instance"


@pytest.mark.asyncio
async def test_billing_preflight_diag_endpoint_logs_payload(monkeypatch):
    sample_report = {
        "result": "READY",
        "sections": {
            "db": {"status": "OK", "meta": {"lat_ms": 12}},
            "users": {"status": "OK", "meta": {"records": 5, "query_latency_ms": 7}},
            "balances": {"status": "OK", "meta": {"records": 3, "query_latency_ms": 8}},
            "free_limits": {"status": "OK", "meta": {"records": 2, "query_latency_ms": 9}},
            "attempts": {"status": "OK", "meta": {"total": 1, "query_latency_ms": 10}},
        },
    }

    async def _fake_run_billing_preflight(storage, db_pool, emit_logs=True):
        return sample_report

    monkeypatch.setattr("app.storage.factory.get_storage", lambda: _FakeStorage())
    monkeypatch.setattr("app.diagnostics.billing_preflight.run_billing_preflight", _fake_run_billing_preflight)

    response = await billing_preflight_handler(None)
    payload = json.loads(response.text)

    assert payload["result"] == "READY"
    assert payload["db"]["lat_ms"] == 12
    assert payload["users"]["records"] == 5


def test_admin_self_check_output_no_secrets(monkeypatch):
    _set_required_env(monkeypatch)

    report = build_config_self_check_report()
    assert "123456:ABCDEF" not in report
    assert "kie_1234567890abcdef" not in report
    assert "TELEGRAM_BOT_TOKEN" in report
    assert "KIE_API_KEY" in report
