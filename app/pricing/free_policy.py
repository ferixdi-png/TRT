"""Free daily quota policy based on SSOT."""
from __future__ import annotations

from typing import Set

from app.pricing.ssot_catalog import get_free_sku_ids

_FREE_DAILY_LIMIT = 5


def get_free_daily_limit() -> int:
    return _FREE_DAILY_LIMIT


def list_free_skus() -> Set[str]:
    return set(get_free_sku_ids())


def is_sku_free_daily(sku_id: str) -> bool:
    if not sku_id:
        return False
    return sku_id in list_free_skus()
