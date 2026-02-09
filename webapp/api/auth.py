"""Telegram WebApp authentication."""
import hashlib
import hmac
import json
import os
import urllib.parse
from typing import Optional, Dict, Any

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


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
    user_data = validate_webapp_data(init_data)
    if user_data and "id" in user_data:
        return int(user_data["id"])
    return None
