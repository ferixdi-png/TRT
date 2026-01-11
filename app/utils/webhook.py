"""
Webhook utilities for building webhook URLs from environment variables.
"""

import asyncio
import os
from typing import Callable, Coroutine, Optional, TypeVar

from app.utils.logging_config import get_logger
from app.utils.mask import mask

logger = get_logger(__name__)

T = TypeVar("T")


def get_webhook_base_url() -> str:
    """Return webhook base URL, preferring WEBHOOK_URL as a legacy alias."""
    return (
        os.getenv("WEBHOOK_URL", "").strip()
        or os.getenv("WEBHOOK_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    )


def derive_webhook_secret_path(token: str) -> str:
    """Derive a stable URL-safe secret path.

    Why:
    - Telegram webhook URL path must be URL-safe (':' is awkward)
    - Repo historically used bot token with ':' removed, which works
    - Keeping the same derivation avoids silent 404s after redeploys

    Implementation:
    - strip
    - remove ':'
    - keep last 64 chars (stable, not too long)
    """

    cleaned = (token or "").strip().replace(":", "")
    if len(cleaned) > 64:
        cleaned = cleaned[-64:]
    return cleaned


def get_webhook_secret_path(default: str = "") -> str:
    """Return the secret path used in webhook URL construction."""
    # Explicit override (optional)
    explicit = os.getenv("WEBHOOK_SECRET_PATH", "").strip()
    if explicit:
        return derive_webhook_secret_path(explicit)

    token = os.getenv("TELEGRAM_BOT_TOKEN", default)
    return derive_webhook_secret_path(token)


def get_webhook_secret_token() -> str:
    """Return the secret token used to validate webhook requests."""
    return os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()


def get_kie_callback_path(default: str = "callbacks/kie") -> str:
    """Return path segment for KIE callbacks (no leading slash)."""
    path = os.getenv("KIE_CALLBACK_PATH", "").strip().strip("/")
    return path or default


def build_kie_callback_url(base_url: str | None = None, path: str | None = None) -> str:
    """Build KIE callback URL from base and path.

    Falls back to env WEBHOOK_BASE_URL/WEBHOOK_URL/RENDER_EXTERNAL_URL.
    """
    base = (base_url or get_webhook_base_url()).rstrip("/")
    segment = (path or get_kie_callback_path()).strip("/")
    if not base or not segment:
        return ""
    return f"{base}/{segment}"


def build_webhook_url(base_url: str, secret_path: str) -> str:
    """Build full webhook URL from base and secret path."""
    if not base_url or not secret_path:
        return ""
    return f"{base_url.rstrip('/')}/webhook/{secret_path}"


def mask_webhook_url(url: str, secret_path: Optional[str] = None) -> str:
    """Mask webhook URL to avoid leaking secret path in logs."""
    if not url:
        return ""
    if secret_path and secret_path in url:
        return url.replace(secret_path, mask(secret_path))
    prefix, separator, secret = url.partition("/webhook/")
    if not separator:
        return url
    return f"{prefix}{separator}{mask(secret)}"


async def _call_with_retry(
    label: str,
    func: Callable[[], Coroutine[None, None, T]],
    timeout_s: float,
    retries: int,
    backoff_s: float,
) -> T:
    """Run an async callable with retries and timeout."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await asyncio.wait_for(func(), timeout=timeout_s)
        except Exception as exc:  # noqa: BLE001 - surface last error after retries
            last_error = exc
            if attempt == retries:
                logger.error("[WEBHOOK] %s failed after %s attempts: %s", label, retries, exc)
                raise
            delay = backoff_s * attempt
            logger.warning(
                "[WEBHOOK] %s attempt %s/%s failed: %s. Retrying in %.1fs",
                label,
                attempt,
                retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise last_error if last_error else RuntimeError(f"{label} failed")


async def ensure_webhook(
    bot,
    webhook_url: str,
    secret_token: Optional[str] = None,
    timeout_s: float = 10.0,
    retries: int = 3,
    backoff_s: float = 1.0,
) -> bool:
    """Ensure the webhook is configured without flapping."""
    if not webhook_url:
        return False

    desired_url = webhook_url.rstrip("/")
    webhook_info = await _call_with_retry(
        "get_webhook_info",
        bot.get_webhook_info,
        timeout_s=timeout_s,
        retries=retries,
        backoff_s=backoff_s,
    )
    current_url = (webhook_info.url or "").rstrip("/")
    if current_url == desired_url:
        logger.info("[WEBHOOK] Webhook already set to %s", mask_webhook_url(webhook_url))
        return True

    async def _set_webhook() -> None:
        await bot.set_webhook(webhook_url, secret_token=secret_token or None)

    await _call_with_retry(
        "set_webhook",
        _set_webhook,
        timeout_s=timeout_s,
        retries=retries,
        backoff_s=backoff_s,
    )
    logger.info("[WEBHOOK] Webhook set to %s", mask_webhook_url(webhook_url))
    return True
