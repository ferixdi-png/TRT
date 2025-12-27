"""Callback registry for Telegram callback_data.

Telegram has a hard limit of 64 bytes for callback_data.

We prefer **direct** callback_data (prefix:raw_id) when it fits.
If it doesn't fit, we fall back to an in-memory short key (prefix:HASH).

Important: in-memory keys do NOT survive restarts. Handlers must gracefully
handle "stale" callbacks by asking user to refresh (/start).
"""
import hashlib
import base64
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Telegram callback_data hard limit.
TG_CALLBACK_LIMIT = 64

# In-memory registry: short_key -> original_id
_registry: Dict[str, str] = {}
_reverse: Dict[str, str] = {}  # original_id -> short_key


def _hash_id(raw_id: str) -> str:
    """Generate short hash from ID (10 chars base64url)."""
    digest = hashlib.sha1(raw_id.encode('utf-8')).digest()
    b64 = base64.urlsafe_b64encode(digest[:8]).decode('ascii').rstrip('=')
    return b64[:10]  # 10 chars max


def make_key(prefix: str, raw_id: str) -> str:
    """
    Create short callback key from prefix and raw ID.
    
    Format: prefix:HASH (e.g., "m:Ab12Cd34Ef")
    
    Args:
        prefix: Category prefix (m=model, f=format, etc.)
        raw_id: Original ID (may be long)
        
    Returns:
        Short key suitable for callback_data (<= 20 chars)
    """
    if not raw_id:
        return prefix

    # Prefer direct callback_data when it fits Telegram's 64-byte limit.
    direct = f"{prefix}:{raw_id}"
    if len(direct.encode("utf-8")) <= TG_CALLBACK_LIMIT:
        return direct
    
    # Check if already registered
    cache_key = f"{prefix}:{raw_id}"
    if cache_key in _reverse:
        return _reverse[cache_key]
    
    # Generate new short key
    short_hash = _hash_id(raw_id)
    short_key = f"{prefix}:{short_hash}"
    
    # Register both directions
    _registry[short_key] = raw_id
    _reverse[cache_key] = short_key
    
    logger.debug(f"Registered callback: {short_key} -> {raw_id}")
    
    return short_key


def resolve_key(key: str) -> Optional[str]:
    """
    Resolve short key back to original ID.
    
    Args:
        key: Short callback key (e.g., "m:Ab12Cd34Ef")
        
    Returns:
        Original ID or None if not found
    """
    if not key or ':' not in key:
        return None

    # We always return the *payload only* (without prefix), so handlers can
    # treat it as the real ID.
    prefix, rest = key.split(':', 1)

    # If this looks like a short hash key (base36, 6 chars) but registry doesn't know it,
    # it's most likely a stale button from a previous deploy.
    looks_like_hash = len(rest) == 6 and rest.isalnum() and rest == rest.lower()

    # Direct form (prefix:payload). Return payload unless it looks like an unresolved hash.
    if len(key.encode("utf-8")) <= TG_CALLBACK_LIMIT and key not in _registry:
        return None if looks_like_hash else rest

    # Short key form (prefix:HASH) stored in memory
    original = _registry.get(key)
    if not original:
        # Stale callback (e.g., after restart) — handler should ask user to refresh (/start).
        return None

    return original


def init_registry_from_models(models_dict: Dict[str, dict]) -> None:
    """
    Pre-populate registry from SOURCE_OF_TRUTH models.
    
    Args:
        models_dict: Dict of model_id -> model config
    """
    logger.info(f"Initializing callback registry with {len(models_dict)} models")
    
    for model_id in models_dict.keys():
        make_key("m", model_id)  # m: = model
        make_key("gen", model_id)  # gen: = generation
        make_key("card", model_id)  # card: = model card
    
    logger.info(f"Callback registry initialized: {len(_registry)} keys")


def validate_callback_length(callback_data: str) -> bool:
    """
    Validate callback_data doesn't exceed Telegram's 64-byte limit.
    
    Args:
        callback_data: Callback data string
        
    Returns:
        True if valid length
        
    Raises:
        ValueError if exceeds limit
    """
    byte_length = len(callback_data.encode('utf-8'))
    
    if byte_length > TG_CALLBACK_LIMIT:
        raise ValueError(
            f"callback_data exceeds {TG_CALLBACK_LIMIT} bytes: {byte_length} bytes\n"
            f"Data: {callback_data[:100]}"
        )
    
    return True


def get_stats() -> Dict[str, int]:
    """Get registry statistics."""
    return {
        "total_keys": len(_registry),
        "unique_ids": len(set(_registry.values()))
    }
