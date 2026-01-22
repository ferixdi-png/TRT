import os
from typing import Set

_admin_ids_cache: Set[int] | None = None


def _load_admin_ids() -> Set[int]:
    ids_env = os.getenv("ADMIN_IDS", "").strip()
    admin_id_env = os.getenv("ADMIN_ID", "").strip()
    ids: Set[int] = set()
    if ids_env:
        for part in ids_env.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                continue
    if admin_id_env:
        try:
            ids.add(int(admin_id_env))
        except ValueError:
            pass
    return ids


def is_admin(user_id: int) -> bool:
    """Check admin rights using ADMIN_IDS or fallback to ADMIN_ID."""
    global _admin_ids_cache
    if _admin_ids_cache is None:
        _admin_ids_cache = _load_admin_ids()
    return user_id in _admin_ids_cache
