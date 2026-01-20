import json

import pytest

from app.config_env import (
    REQUIRED_ENV,
    ConfigValidationError,
    build_config_self_check_report,
    mask_secrets_in_text,
    validate_config,
)
from app.storage.github_storage import GitHubStorage
from app.utils.healthcheck import health_handler


def _set_required_env(monkeypatch, overrides=None):
    values = {
        "ADMIN_ID": "123",
        "BOT_INSTANCE_ID": "partner-instance",
        "BOT_MODE": "webhook",
        "GITHUB_BRANCH": "main",
        "GITHUB_COMMITTER_EMAIL": "bot@example.com",
        "GITHUB_COMMITTER_NAME": "Partner Bot",
        "GITHUB_REPO": "owner/repo",
        "GITHUB_TOKEN": "ghp_1234567890abcdef",
        "KIE_API_KEY": "kie_1234567890abcdef",
        "PAYMENT_BANK": "Test Bank",
        "PAYMENT_CARD_HOLDER": "Test Holder",
        "PAYMENT_PHONE": "+1234567890",
        "PORT": "8080",
        "STORAGE_MODE": "github",
        "STORAGE_PREFIX": "storage",
        "SUPPORT_TELEGRAM": "@supportuser",
        "SUPPORT_TEXT": "Support text",
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
    github = "ghp_1234567890abcdef"
    kie = "kie_1234567890abcdef"
    log_line = f"Tokens: {token} {github} {kie}"
    masked = mask_secrets_in_text(
        log_line,
        {
            "TELEGRAM_BOT_TOKEN": token,
            "GITHUB_TOKEN": github,
            "KIE_API_KEY": kie,
        },
    )
    assert token not in masked
    assert github not in masked
    assert kie not in masked


def test_storage_namespace_isolation(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("GITHUB_STORAGE_STUB", "1")

    monkeypatch.setenv("BOT_INSTANCE_ID", "alpha")
    storage_alpha = GitHubStorage()
    path_alpha = storage_alpha._storage_path("user_balances.json")

    monkeypatch.setenv("BOT_INSTANCE_ID", "beta")
    storage_beta = GitHubStorage()
    path_beta = storage_beta._storage_path("user_balances.json")

    assert path_alpha != path_beta
    assert "alpha" in path_alpha
    assert "beta" in path_beta


@pytest.mark.asyncio
async def test_health_endpoint_ok(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setenv("BOT_INSTANCE_ID", "partner-instance")

    response = await health_handler(None)
    payload = json.loads(response.text)
    assert payload["ok"] is True
    assert payload["bot_mode"] == "webhook"
    assert payload["instance"] == "partner-instance"


def test_admin_self_check_output_no_secrets(monkeypatch):
    _set_required_env(monkeypatch)

    report = build_config_self_check_report()
    assert "123456:ABCDEF" not in report
    assert "ghp_1234567890abcdef" not in report
    assert "kie_1234567890abcdef" not in report
    assert "TELEGRAM_BOT_TOKEN" in report
    assert "GITHUB_TOKEN" in report
    assert "KIE_API_KEY" in report
