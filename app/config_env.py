"""Environment configuration and validation utilities."""
from __future__ import annotations

import os
import re
import sys
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

REQUIRED_ENV: Tuple[str, ...] = (
    "ADMIN_ID",
    "BOT_INSTANCE_ID",
    "BOT_MODE",
    "GITHUB_BRANCH",
    "GITHUB_COMMITTER_EMAIL",
    "GITHUB_COMMITTER_NAME",
    "GITHUB_REPO",
    "GITHUB_TOKEN",
    "KIE_API_KEY",
    "PAYMENT_BANK",
    "PAYMENT_CARD_HOLDER",
    "PAYMENT_PHONE",
    "PORT",
    "STORAGE_PREFIX",
    "SUPPORT_TELEGRAM",
    "SUPPORT_TEXT",
    "TELEGRAM_BOT_TOKEN",
    "WEBHOOK_BASE_URL",
)

OPTIONAL_ENV: Tuple[str, ...] = (
    "ALLOW_REAL_GENERATION",
    "CREDIT_TO_RUB_RATE",
    "DATA_DIR",
    "DRY_RUN",
    "GITHUB_BACKOFF_BASE",
    "GITHUB_MAX_PARALLEL",
    "GITHUB_TIMEOUT_SECONDS",
    "GITHUB_WRITE_RETRIES",
    "GITHUB_ONLY_STORAGE",
    "KIE_API_URL",
    "KIE_RESULT_CDN_BASE_URL",
    "PORT_ALT",
    "PRICE_MULTIPLIER",
    "STORAGE_MODE",
    "STORAGE_GITHUB_BRANCH",
    "STORAGE_GITHUB_REPO",
    "STORAGE_BRANCH",
    "TEST_MODE",
    "WEBHOOK_URL",
)

SECRET_ENV = {
    "TELEGRAM_BOT_TOKEN",
    "GITHUB_TOKEN",
    "KIE_API_KEY",
}

_COMMON_STORAGE_PREFIXES = {"storage", "data", "shared", "default"}


class ConfigValidationError(RuntimeError):
    """Raised when required environment variables are missing or invalid."""

    def __init__(self, missing: List[str], invalid: List[str]):
        super().__init__("Configuration validation failed")
        self.missing = missing
        self.invalid = invalid


@dataclass(frozen=True)
class StoragePrefixResolution:
    effective_prefix: str
    legacy_prefix: Optional[str]


@dataclass(frozen=True)
class ConfigValidationResult:
    missing_required: List[str]
    invalid_required: List[str]
    invalid_optional: List[str]

    @property
    def ok(self) -> bool:
        return not self.missing_required and not self.invalid_required


def _is_valid_url(value: str) -> bool:
    if not value:
        return False
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _is_valid_repo(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value))


def _is_valid_username(value: str) -> bool:
    return bool(re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value))


def _is_valid_branch(value: str) -> bool:
    if not value:
        return False
    if value.startswith("-") or value.endswith("/") or ".." in value or "//" in value:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._/-]+", value))


def _is_valid_instance(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", value))


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def mask_sensitive_envs(env: Dict[str, str]) -> Dict[str, str]:
    masked = dict(env)
    for key in SECRET_ENV:
        if key in masked and masked[key]:
            masked[key] = mask_secret(masked[key])
    return masked


def mask_secrets_in_text(text: str, env: Optional[Dict[str, str]] = None) -> str:
    env_values = env or {k: os.getenv(k, "") for k in SECRET_ENV}
    redacted = text
    for value in env_values.values():
        if value:
            redacted = redacted.replace(value, mask_secret(value))
    return redacted


def resolve_storage_prefix(raw_prefix: str, bot_instance_id: str) -> StoragePrefixResolution:
    normalized = (raw_prefix or "").strip().strip("/")
    legacy_prefix: Optional[str] = None

    if not normalized or normalized in _COMMON_STORAGE_PREFIXES:
        legacy_prefix = normalized or "storage"
        effective = f"storage/{bot_instance_id}" if bot_instance_id else "storage"
        return StoragePrefixResolution(effective_prefix=effective.strip("/"), legacy_prefix=legacy_prefix)

    segments = normalized.split("/")
    if bot_instance_id and bot_instance_id not in segments:
        legacy_prefix = normalized
        effective = f"{normalized}/{bot_instance_id}"
    else:
        effective = normalized

    return StoragePrefixResolution(effective_prefix=effective.strip("/"), legacy_prefix=legacy_prefix)


def validate_config(strict: bool = True) -> ConfigValidationResult:
    missing_required: List[str] = []
    invalid_required: List[str] = []
    invalid_optional: List[str] = []

    def require(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value and name != "STORAGE_PREFIX":
            missing_required.append(name)
        return value

    admin_id = require("ADMIN_ID")
    bot_instance_id = require("BOT_INSTANCE_ID")
    bot_mode = require("BOT_MODE")
    github_branch = require("GITHUB_BRANCH")
    committer_email = require("GITHUB_COMMITTER_EMAIL")
    committer_name = require("GITHUB_COMMITTER_NAME")
    github_repo = require("GITHUB_REPO")
    github_token = require("GITHUB_TOKEN")
    kie_api_key = require("KIE_API_KEY")
    payment_bank = require("PAYMENT_BANK")
    payment_card_holder = require("PAYMENT_CARD_HOLDER")
    payment_phone = require("PAYMENT_PHONE")
    port = os.getenv("PORT", "").strip()
    storage_mode = os.getenv("STORAGE_MODE", "").strip()
    storage_prefix = os.getenv("STORAGE_PREFIX", "").strip()
    support_telegram = require("SUPPORT_TELEGRAM")
    support_text = require("SUPPORT_TEXT")
    telegram_bot_token = require("TELEGRAM_BOT_TOKEN")
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()
    storage_branch = os.getenv("STORAGE_BRANCH", os.getenv("STORAGE_GITHUB_BRANCH", "storage")).strip()

    if bot_mode in {"webhook", "web"}:
        if not port:
            missing_required.append("PORT")
        if not webhook_base_url:
            missing_required.append("WEBHOOK_BASE_URL")

    if admin_id and not admin_id.isdigit():
        invalid_required.append("ADMIN_ID (must be number)")
    if bot_instance_id and not _is_valid_instance(bot_instance_id):
        invalid_required.append("BOT_INSTANCE_ID (letters/numbers/._- only)")
    if bot_mode and bot_mode not in {"polling", "webhook", "web", "smoke"}:
        invalid_required.append("BOT_MODE (polling/webhook/web/smoke)")
    if github_branch and not _is_valid_branch(github_branch):
        invalid_required.append("GITHUB_BRANCH (invalid format)")
    if committer_email and "@" not in committer_email:
        invalid_required.append("GITHUB_COMMITTER_EMAIL (must be email)")
    if not committer_name and "GITHUB_COMMITTER_NAME" not in missing_required:
        invalid_required.append("GITHUB_COMMITTER_NAME (must be non-empty)")
    if github_repo and not _is_valid_repo(github_repo):
        invalid_required.append("GITHUB_REPO (format owner/repo)")
    if github_token and len(github_token) < 10:
        invalid_required.append("GITHUB_TOKEN (appears too short)")
    if kie_api_key and len(kie_api_key) < 10:
        invalid_required.append("KIE_API_KEY (appears too short)")
    if not payment_bank and "PAYMENT_BANK" not in missing_required:
        invalid_required.append("PAYMENT_BANK (must be non-empty)")
    if not payment_card_holder and "PAYMENT_CARD_HOLDER" not in missing_required:
        invalid_required.append("PAYMENT_CARD_HOLDER (must be non-empty)")
    if not payment_phone and "PAYMENT_PHONE" not in missing_required:
        invalid_required.append("PAYMENT_PHONE (must be non-empty)")
    if port and not port.isdigit():
        invalid_required.append("PORT (must be number)")
    if storage_mode and storage_mode not in {"auto", "github", "postgres", "db"}:
        invalid_required.append("STORAGE_MODE (auto/github/postgres/db)")
    if support_telegram and not _is_valid_username(support_telegram):
        invalid_required.append("SUPPORT_TELEGRAM (format @username)")
    if not support_text and "SUPPORT_TEXT" not in missing_required:
        invalid_required.append("SUPPORT_TEXT (must be non-empty)")
    if not telegram_bot_token and "TELEGRAM_BOT_TOKEN" not in missing_required:
        invalid_required.append("TELEGRAM_BOT_TOKEN (must be non-empty)")
    if webhook_base_url and not _is_valid_url(webhook_base_url):
        invalid_required.append("WEBHOOK_BASE_URL (must be URL)")
    if storage_branch and github_branch and storage_branch == github_branch:
        invalid_required.append("STORAGE_BRANCH must differ from GITHUB_BRANCH")

    if storage_prefix and "BOT_INSTANCE_ID" not in missing_required:
        resolution = resolve_storage_prefix(storage_prefix, bot_instance_id)
        if not resolution.effective_prefix:
            invalid_required.append("STORAGE_PREFIX (invalid)")

    optional_url = os.getenv("KIE_API_URL", "").strip()
    if optional_url and not _is_valid_url(optional_url):
        invalid_optional.append("KIE_API_URL (must be URL)")

    result = ConfigValidationResult(
        missing_required=missing_required,
        invalid_required=invalid_required,
        invalid_optional=invalid_optional,
    )

    if strict:
        if missing_required or invalid_required:
            _log_validation_errors(result)
            raise ConfigValidationError(missing_required, invalid_required)
        if invalid_optional:
            _log_validation_warnings(result)
    return result


def _log_validation_errors(result: ConfigValidationResult) -> None:
    logger.error("=" * 60)
    logger.error("CONFIGURATION VALIDATION FAILED")
    logger.error("=" * 60)
    if result.missing_required:
        logger.error("Missing required env vars: %s", ", ".join(result.missing_required))
    if result.invalid_required:
        logger.error("Invalid required env vars: %s", ", ".join(result.invalid_required))
    logger.error("=" * 60)


def _log_validation_warnings(result: ConfigValidationResult) -> None:
    if result.invalid_optional:
        logger.warning("Invalid optional env vars: %s", ", ".join(result.invalid_optional))


def validate_or_exit() -> ConfigValidationResult:
    try:
        result = validate_config(strict=True)
    except ConfigValidationError as exc:
        sys.exit(1)
    return result


def build_config_self_check_report() -> str:
    lines: List[str] = []
    lines.append("🧩 <b>Проверка конфигурации</b>\n")

    lines.append("<b>REQUIRED</b>")
    for name in REQUIRED_ENV:
        value = os.getenv(name, "").strip()
        status = "✅ set" if value else "❌ not set"
        lines.append(f"• {name}: {status}")

    lines.append("\n<b>OPTIONAL</b>")
    for name in OPTIONAL_ENV:
        value = os.getenv(name, "").strip()
        status = "✅ set" if value else "⚪ not set"
        lines.append(f"• {name}: {status}")

    bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
    storage_prefix_raw = os.getenv("STORAGE_PREFIX", "").strip()
    storage_prefix = resolve_storage_prefix(storage_prefix_raw, bot_instance_id).effective_prefix
    webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "").strip()

    lines.append("\n<b>Computed</b>")
    lines.append(f"• BOT_INSTANCE_ID: {bot_instance_id or 'missing'}")
    lines.append(f"• STORAGE_PREFIX: {storage_prefix or 'missing'}")
    lines.append(f"• WEBHOOK_BASE_URL: {webhook_base_url or 'missing'}")

    return "\n".join(lines)
