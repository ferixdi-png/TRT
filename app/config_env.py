"""Environment configuration and validation utilities."""
from __future__ import annotations

import os
import re
import sys
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

REQUIRED_ENV: Tuple[str, ...] = (
    "ADMIN_ID",
    "BOT_INSTANCE_ID",
    "TELEGRAM_BOT_TOKEN",
    "WEBHOOK_BASE_URL",
)

OPTIONAL_ENV: Tuple[str, ...] = (
    "ALLOW_REAL_GENERATION",
    "CREDIT_TO_RUB_RATE",
    "DATA_DIR",
    "DRY_RUN",
    "KIE_API_KEY",
    "KIE_API_URL",
    "KIE_RESULT_CDN_BASE_URL",
    "OWNER_PAYMENT_BANK",
    "OWNER_PAYMENT_CARD_HOLDER",
    "OWNER_PAYMENT_PHONE",
    "OWNER_SUPPORT_TELEGRAM",
    "OWNER_SUPPORT_TEXT",
    "PORT_ALT",
    "PRICE_MULTIPLIER",
    "STORAGE_MODE",
    "TEST_MODE",
    "WEBHOOK_URL",
    # остальные опциональные
)

SECRET_ENV = {
    "TELEGRAM_BOT_TOKEN",
    "KIE_API_KEY",
}

_COMMON_STORAGE_PREFIXES = {"storage", "data", "shared", "default"}
_INSTANCE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
_ENV_EXAMPLES = {
    "TELEGRAM_BOT_TOKEN": "123456:ABCDEF",
    "ADMIN_ID": "123456789",
    "BOT_INSTANCE_ID": "partner-01",
    "WEBHOOK_BASE_URL": "https://your-service.onrender.com",
}


class ConfigValidationError(RuntimeError):
    """Raised when required environment variables are missing or invalid."""

    def __init__(self, missing: List[str], invalid: List[str]):
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if invalid:
            details.append(f"invalid: {', '.join(invalid)}")
        message = "Configuration validation failed"
        if details:
            message = f"{message} ({'; '.join(details)})"
        super().__init__(message)
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


def is_valid_instance_slug(value: str) -> bool:
    """Validate short BOT_INSTANCE_ID slug (3-32 chars, lowercase, no spaces)."""
    if not value:
        return False
    return bool(_INSTANCE_SLUG_RE.fullmatch(value))


def _is_valid_instance(value: str) -> bool:
    return is_valid_instance_slug(value)


def _is_valid_webhook_base_url(value: str) -> bool:
    if not value:
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc)


def normalize_webhook_base_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    path = parts.path or ""
    while "//" in path:
        path = path.replace("//", "/")
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")


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
    telegram_bot_token = require("TELEGRAM_BOT_TOKEN")
    webhook_base_url_raw = os.getenv("WEBHOOK_BASE_URL", "").strip()
    if not webhook_base_url_raw:
        missing_required.append("WEBHOOK_BASE_URL")
    webhook_base_url = normalize_webhook_base_url(webhook_base_url_raw)
    if webhook_base_url_raw and webhook_base_url and webhook_base_url != webhook_base_url_raw:
        logger.info("WEBHOOK_BASE_URL normalized: %s -> %s", webhook_base_url_raw, webhook_base_url)
    kie_api_key = os.getenv("KIE_API_KEY", "").strip()
    storage_mode = os.getenv("STORAGE_MODE", "").strip().lower()
    # DB-only runtime: github переменные не требуются
    committer_email = ""
    committer_name = ""
    bot_mode = os.getenv("BOT_MODE", "").strip()
    port = os.getenv("PORT", "").strip()
    storage_prefix = os.getenv("STORAGE_PREFIX", "").strip()
    payment_bank = os.getenv("PAYMENT_BANK", "").strip()
    payment_card_holder = os.getenv("PAYMENT_CARD_HOLDER", "").strip()
    payment_phone = os.getenv("PAYMENT_PHONE", "").strip()
    support_telegram = os.getenv("SUPPORT_TELEGRAM", "").strip()
    support_text = os.getenv("SUPPORT_TEXT", "").strip()

    if bot_mode in {"webhook", "web"}:
        if not port:
            missing_required.append("PORT")
        if not webhook_base_url:
            missing_required.append("WEBHOOK_BASE_URL")

    if admin_id:
        admin_parts = [p for p in re.split(r"[,\s]+", admin_id.strip()) if p]
        if not admin_parts or any(not part.isdigit() for part in admin_parts):
            invalid_required.append("ADMIN_ID (must be number or list of numbers)")
    if bot_instance_id:
        if " " in bot_instance_id or not _is_valid_instance(bot_instance_id):
            invalid_required.append("BOT_INSTANCE_ID (slug: lowercase letters/numbers/._- only)")
        if not (3 <= len(bot_instance_id) <= 32):
            invalid_required.append("BOT_INSTANCE_ID (length 3-32)")
    if bot_mode and bot_mode not in {"polling", "webhook", "web", "smoke"}:
        invalid_required.append("BOT_MODE (polling/webhook/web/smoke)")
    if kie_api_key and len(kie_api_key) < 10:
        invalid_optional.append("KIE_API_KEY (appears too short)")
    if port and not port.isdigit():
        invalid_required.append("PORT (must be number)")
    if storage_mode and storage_mode not in {"auto", "postgres", "db"}:
        invalid_optional.append("STORAGE_MODE (auto/postgres/db)")
    if support_telegram and not _is_valid_username(support_telegram):
        invalid_optional.append("SUPPORT_TELEGRAM (format @username)")
    if not telegram_bot_token and "TELEGRAM_BOT_TOKEN" not in missing_required:
        invalid_required.append("TELEGRAM_BOT_TOKEN (must be non-empty)")
    if webhook_base_url_raw and not _is_valid_webhook_base_url(webhook_base_url_raw):
        invalid_required.append("WEBHOOK_BASE_URL (must be https:// URL)")
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
        for name in result.missing_required:
            example = _ENV_EXAMPLES.get(name, f"{name}=<value>")
            logger.error("MISSING_ENV %s. How to fix: set %s", name, example)
    if result.invalid_required:
        logger.error("Invalid required env vars: %s", ", ".join(result.invalid_required))
        for name in result.invalid_required:
            logger.error("INVALID_ENV %s. How to fix: check formatting and redeploy.", name)
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
    webhook_base_url = normalize_webhook_base_url(os.getenv("WEBHOOK_BASE_URL", "").strip())

    lines.append("\n<b>Computed</b>")
    lines.append(f"• BOT_INSTANCE_ID: {bot_instance_id or 'missing'}")
    lines.append(f"• STORAGE_PREFIX: {storage_prefix or 'missing'}")
    lines.append(f"• WEBHOOK_BASE_URL: {webhook_base_url or 'missing'}")

    if not os.getenv("KIE_API_KEY"):
        lines.append("\n⚠️ <b>AI key not set</b>: KIE_API_KEY is missing, AI generation will be disabled.")

    return "\n".join(lines)
