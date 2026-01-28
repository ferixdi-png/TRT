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


def is_fast_tools_free_sku(sku_id: str, source: str) -> bool:
    """
    Check if free generation is allowed for this SKU.
    Free access is only available through FAST TOOLS and only for top-5 cheapest SKUs.
    """
    if not sku_id or source != "fast_tools":
        return False
    
    # Get all free SKUs and filter to only top-5 cheapest
    from app.pricing.ssot_catalog import get_all_skus_with_pricing
    
    free_skus = list_free_skus()
    all_skus = get_all_skus_with_pricing()
    
    # Filter to only free SKUs that exist in pricing
    free_skus_with_price = []
    for free_sku_id in free_skus:
        if free_sku_id in all_skus:
            price = all_skus[free_sku_id].get("price_rub", 0)
            free_skus_with_price.append((free_sku_id, price))
    
    # Sort by price (cheapest first) and take top-5
    free_skus_with_price.sort(key=lambda x: x[1])
    top_5_skus = set(sku_id for sku_id, _ in free_skus_with_price[:5])
    
    return sku_id in top_5_skus
