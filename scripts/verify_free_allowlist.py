"""Verify that free daily allowlist and limit are correctly configured."""
from __future__ import annotations

import sys

from app.pricing.free_policy import get_free_daily_limit, list_free_skus
from app.pricing.ssot_catalog import get_sku_by_id


def main() -> int:
    daily_limit = get_free_daily_limit()
    free_skus = sorted(list_free_skus())

    print(f"daily_free_limit={daily_limit}")
    if not free_skus:
        print("free_skus=EMPTY")
        return 1

    print("free_skus:")
    for sku_id in free_skus:
        sku = get_sku_by_id(sku_id)
        sku_name = sku.title if sku else "(unknown)"
        print(f"- {sku_id} :: {sku_name}")

    if daily_limit != 5:
        print("error: daily_free_limit must be 5")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
