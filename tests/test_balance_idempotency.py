import pytest

from app.storage.json_storage import JsonStorage


@pytest.mark.asyncio
async def test_charge_balance_once_idempotent(tmp_path):
    storage = JsonStorage(data_dir=str(tmp_path))
    await storage.set_user_balance(1, 100.0)

    result_first = await storage.charge_balance_once(
        1,
        25.0,
        task_id="task-123",
        sku_id="sku-test",
        model_id="model-test",
    )
    result_second = await storage.charge_balance_once(
        1,
        25.0,
        task_id="task-123",
        sku_id="sku-test",
        model_id="model-test",
    )

    balance = await storage.get_user_balance(1)
    assert result_first["status"] == "charged"
    assert result_second["status"] == "duplicate"
    assert balance == 75.0
