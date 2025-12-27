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
_reverse: Dict[str, str] = {}  # cache_key (prefix:raw_id) -> short_key


def _hash_id_v2(raw_id: str) -> str:
    """Current short hash (10 chars, base64url-ish).

    We intentionally keep this compact and URL-safe.
    """
    digest = hashlib.sha1(raw_id.encode("utf-8")).digest()
    b64 = base64.urlsafe_b64encode(digest[:8]).decode("ascii").rstrip("=")
    return b64[:10]


def _hash_id_v1(raw_id: str) -> str:
    """Legacy short hash (6 chars lowercase hex).

    Older builds used 6-char lowercase-ish hashes. Supporting it keeps
    old messages' buttons working after deploys.
    """
    return hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:6]


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
    # Generate short key(s)
    short_hash_v2 = _hash_id_v2(raw_id)
    short_key_v2 = f"{prefix}:{short_hash_v2}"

    # Register both directions (v2)
    _registry[short_key_v2] = raw_id
    _reverse[cache_key] = short_key_v2

    # Also register legacy key (v1) so old callbacks still resolve.
    short_hash_v1 = _hash_id_v1(raw_id)
    short_key_v1 = f"{prefix}:{short_hash_v1}"
    _registry.setdefault(short_key_v1, raw_id)
    
    logger.debug(
        f"Registered callback: {short_key_v2} (v2) / {short_key_v1} (v1) -> {raw_id}"
    )

    return short_key_v2


def _register_hashes(prefix: str, raw_id: str) -> None:
    """Register both legacy (v1) and current (v2) hash keys.

    Why this exists: after deploy/restart, users can still press old buttons
    from previous messages. Those buttons might contain hashed callback_data
    even if the current build now uses direct IDs. Pre-registering hashes for
    *all* models makes those old callbacks resolve cleanly.
    """
    short_key_v2 = f"{prefix}:{_hash_id_v2(raw_id)}"
    short_key_v1 = f"{prefix}:{_hash_id_v1(raw_id)}"
    _registry.setdefault(short_key_v2, raw_id)
    _registry.setdefault(short_key_v1, raw_id)


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

    # Direct form (prefix:payload). If it's not a known short key, treat it as payload.
    # If payload looks like a legacy hash (6 hex), we only accept it if we have it in registry;
    # otherwise it's a stale button from another deploy.
    looks_like_v1_hash = len(rest) == 6 and all(c in "0123456789abcdef" for c in rest)

    if len(key.encode("utf-8")) <= TG_CALLBACK_LIMIT and key not in _registry:
        return None if looks_like_v1_hash else rest

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
        # Always register both hashed variants, even if current menus will
        # use the direct form (prefix:...); this prevents "stale button" for
        # users clicking old messages after restart/deploy.
        _register_hashes("m", model_id)
        _register_hashes("gen", model_id)
        _register_hashes("card", model_id)

        # Warm the cache for current direct-vs-hash decision.
        make_key("m", model_id)  # m: = model
        make_key("gen", model_id)  # gen: = generation
        make_key("card", model_id)  # card: = model card
    
    # Useful in logs: most model IDs fit directly, so _registry can be small.
    direct_count = 0
    for model_id in models_dict.keys():
        if len(f"m:{model_id}".encode("utf-8")) <= TG_CALLBACK_LIMIT:
            direct_count += 1
    logger.info(
        f"Callback registry initialized: {len(_registry)} hashed keys, {direct_count} direct keys"
    )


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
