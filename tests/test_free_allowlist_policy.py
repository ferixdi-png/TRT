import pytest

from app.pricing.ssot_catalog import get_free_sku_ids
from app.services import free_tools_service


@pytest.mark.asyncio
async def test_free_allowlist_consumes_only_free_skus(test_env):
    user_id = 4242
    free_sku_ids = get_free_sku_ids()
    assert free_sku_ids
    free_sku_id = free_sku_ids[0]
    non_free_sku_id = "paid-sku"

    before = await free_tools_service.get_free_counter_snapshot(user_id)

    result_non_free = await free_tools_service.consume_free_generation(user_id, non_free_sku_id)
    after_non_free = await free_tools_service.get_free_counter_snapshot(user_id)

    assert result_non_free["status"] == "not_free_sku"
    assert after_non_free["remaining"] == before["remaining"]

    result_free = await free_tools_service.consume_free_generation(user_id, free_sku_id)
    assert result_free["status"] == "ok"

    after_free = await free_tools_service.get_free_counter_snapshot(user_id)
    assert after_free["remaining"] == max(0, before["remaining"] - 1)
