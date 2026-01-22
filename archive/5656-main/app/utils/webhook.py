"""
Webhook utilities - helper functions for webhook configuration
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_webhook_base_url() -> str:
    """
    Get webhook base URL from environment variable.
    
    Returns:
        WEBHOOK_BASE_URL environment variable value, or empty string if not set.
    """
    return os.getenv("WEBHOOK_BASE_URL", "").strip()


def get_webhook_secret_token() -> str:
    """
    Get webhook secret token from environment variable.
    
    Returns:
        WEBHOOK_SECRET_TOKEN environment variable value, or empty string if not set.
    """
    return os.getenv("WEBHOOK_SECRET_TOKEN", "").strip()


def get_kie_callback_path() -> str:
    """
    Get KIE callback path from environment variable.
    
    Returns:
        KIE_CALLBACK_PATH environment variable value, or '/kie/callback' if not set.
    """
    return os.getenv("KIE_CALLBACK_PATH", "/kie/callback").strip()


def build_kie_callback_url(webhook_base_url: str, callback_path: str) -> str:
    """
    Build KIE callback URL from base URL and path.
    
    Args:
        webhook_base_url: Base URL for webhook (e.g., https://example.com)
        callback_path: Callback path (e.g., /kie/callback)
    
    Returns:
        Full callback URL, or empty string if webhook_base_url is not set.
    """
    if not webhook_base_url:
        return ""
    base = webhook_base_url.rstrip("/")
    path = callback_path.lstrip("/")
    return f"{base}/{path}" if base and path else ""


async def ensure_webhook(
    bot,
    webhook_url: str,
    secret_token: str = None,
    force_reset: bool = False,
) -> bool:
    """
    Ensure webhook is set on Telegram bot.
    
    Args:
        bot: Telegram bot instance
        webhook_url: Full webhook URL to set
        secret_token: Optional secret token for webhook security
        force_reset: If True, delete existing webhook before setting new one
    
    Returns:
        True if webhook was set successfully, False otherwise.
    """
    try:
        if force_reset:
            await bot.delete_webhook(drop_pending_updates=False)
        
        await bot.set_webhook(
            url=webhook_url,
            secret_token=secret_token,
            drop_pending_updates=False,
        )
        return True
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to set webhook: {e}")
        return False

