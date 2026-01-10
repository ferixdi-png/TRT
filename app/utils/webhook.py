"""
Webhook utilities for building webhook URLs from environment variables.
"""

from __future__ import annotations

import hashlib
import os


def get_webhook_base_url() -> str:
    """Return webhook base URL, preferring WEBHOOK_URL as a legacy alias."""
    return os.getenv("WEBHOOK_URL", "").strip() or os.getenv("WEBHOOK_BASE_URL", "").strip()


def get_webhook_secret_path() -> str:
    """
    Return the secret path used in webhook URL construction.

    Prefer WEBHOOK_SECRET; fallback to sha256(ADMIN_ID + TELEGRAM_BOT_TOKEN).
    """
    explicit_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if explicit_secret:
        return explicit_secret

    admin_id = os.getenv("ADMIN_ID", "").strip()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not admin_id or not token:
        return ""

    source = f"{admin_id}{token}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def get_webhook_secret_token() -> str:
    """
    Return optional secret token for header validation.

    This should match X-Telegram-Bot-Api-Secret-Token when configured.
    """
    return os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()


def build_webhook_url(base_url: str, secret_path: str) -> str:
    """Build full webhook URL from base and secret path."""
    if not base_url or not secret_path:
        return ""
    return f"{base_url.rstrip('/')}/webhook/{secret_path}"
