"""Telegram WebApp authentication."""
import hashlib
import hmac
import json
import logging
import os
import urllib.parse
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Use BOT_TOKEN or TELEGRAM_BOT_TOKEN as fallback
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
if not BOT_TOKEN:
    logger.warning("WEBAPP_AUTH_NO_TOKEN: Neither BOT_TOKEN nor TELEGRAM_BOT_TOKEN is set")


def validate_webapp_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Validate Telegram WebApp initData.
    
    Returns user data if valid, None otherwise.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not BOT_TOKEN:
        return None
    
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        received_hash = parsed.pop("hash", "")
        
        if not received_hash:
            return None
        
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        
        user_data = parsed.get("user")
        if user_data:
            return json.loads(user_data)
        
        return parsed
        
    except Exception:
        return None


def get_user_id_from_init_data(init_data: str) -> Optional[int]:
    """Extract user_id from validated initData."""
    if not init_data:
        logger.warning("WEBAPP_AUTH_FAIL reason=no_init_data")
        return None
    if not BOT_TOKEN:
        logger.warning("WEBAPP_AUTH_FAIL reason=no_bot_token")
        return None
    user_data = validate_webapp_data(init_data)
    if user_data and "id" in user_data:
        user_id = int(user_data["id"])
        logger.debug("WEBAPP_AUTH_OK user_id=%s", user_id)
        return user_id
    logger.warning("WEBAPP_AUTH_FAIL reason=validation_failed init_data_len=%d", len(init_data))
    return None
