import os
import re
from typing import Set

_admin_ids_cache: Set[int] | None = None


def _parse_ids(value: str) -> Set[int]:
    ids: Set[int] = set()
    for part in re.split(r"[,\s]+", value.strip()):
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def _load_admin_ids() -> Set[int]:
    ids_env = os.getenv("ADMIN_IDS", "").strip()
    admin_id_env = os.getenv("ADMIN_ID", "").strip()
    ids: Set[int] = set()
    if ids_env:
        ids.update(_parse_ids(ids_env))
    if admin_id_env:
        ids.update(_parse_ids(admin_id_env))
    return ids


def get_admin_ids() -> Set[int]:
    """Return cached admin IDs parsed from ADMIN_ID/ADMIN_IDS."""
    global _admin_ids_cache
    if _admin_ids_cache is None:
        _admin_ids_cache = _load_admin_ids()
    return set(_admin_ids_cache)


def reset_admin_ids_cache() -> None:
    """Clear cached admin IDs (useful for tests)."""
    global _admin_ids_cache
    _admin_ids_cache = None


def is_admin(user_id: int) -> bool:
    """Check admin rights using ADMIN_IDS or fallback to ADMIN_ID."""
    return user_id in get_admin_ids()


_bot_owner_ids_cache: Set[int] | None = None


def _load_bot_owner_ids() -> Set[int]:
    """Load bot owner IDs from BOT_OWNER_ID or BOT_OWNER_IDS env vars."""
    ids_env = os.getenv("BOT_OWNER_IDS", "").strip()
    owner_id_env = os.getenv("BOT_OWNER_ID", "").strip()
    ids: Set[int] = set()
    if ids_env:
        ids.update(_parse_ids(ids_env))
    if owner_id_env:
        ids.update(_parse_ids(owner_id_env))
    return ids


def get_bot_owner_ids() -> Set[int]:
    """Return cached bot owner IDs parsed from BOT_OWNER_ID/BOT_OWNER_IDS."""
    global _bot_owner_ids_cache
    if _bot_owner_ids_cache is None:
        _bot_owner_ids_cache = _load_bot_owner_ids()
    return set(_bot_owner_ids_cache)


def is_bot_owner(user_id: int) -> bool:
    """Check if user is bot owner (partner) - has access to admin panel."""
    return user_id in get_bot_owner_ids()


def is_admin_or_owner(user_id: int) -> bool:
    """Check if user is admin OR bot owner - both have admin panel access."""
    return is_admin(user_id) or is_bot_owner(user_id)
