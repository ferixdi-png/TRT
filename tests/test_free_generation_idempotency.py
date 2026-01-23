import pytest

from app.storage.json_storage import JsonStorage


@pytest.mark.asyncio
async def test_consume_free_generation_once_idempotent(tmp_path):
    storage = JsonStorage(data_dir=str(tmp_path))

    result_first = await storage.consume_free_generation_once(
        1,
        task_id="task-free-1",
        sku_id="free-sku",
    )
    result_second = await storage.consume_free_generation_once(
        1,
        task_id="task-free-1",
        sku_id="free-sku",
    )

    assert result_first["status"] == "ok"
    assert result_second["status"] == "duplicate"
    assert result_first["used_today"] == result_second["used_today"]
