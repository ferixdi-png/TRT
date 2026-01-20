import pytest

from app.services.free_tools_service import (
    check_and_consume_free_generation,
    get_free_counter_snapshot,
    get_free_tools_model_ids,
)


@pytest.mark.asyncio
async def test_free_counter_decrements(test_env):
    user_id = 9001
    sku_id = get_free_tools_model_ids()[0]
    before = await get_free_counter_snapshot(user_id)
    result = await check_and_consume_free_generation(user_id, sku_id)
    assert result["status"] == "ok"
    after = await get_free_counter_snapshot(user_id)
    assert after["remaining"] == max(0, before["remaining"] - 1)
