"""
Webhook utilities for building webhook URLs from environment variables.
"""

import os


def get_webhook_base_url() -> str:
    """Return webhook base URL, preferring WEBHOOK_URL as a legacy alias."""
    return os.getenv("WEBHOOK_URL", "").strip() or os.getenv("WEBHOOK_BASE_URL", "").strip()


def get_webhook_secret_path(default: str = "") -> str:
    """Return the secret path used in webhook URL construction."""
    return os.getenv("TELEGRAM_BOT_TOKEN", default).strip()


def build_webhook_url(base_url: str, secret_path: str) -> str:
    """Build full webhook URL from base and secret path."""
    if not base_url or not secret_path:
        return ""
    return f"{base_url.rstrip('/')}/webhook/{secret_path}"
