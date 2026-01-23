import math
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


@pytest.mark.asyncio
async def test_charge_balance_once_rejects_non_positive_amount(tmp_path):
    storage = JsonStorage(data_dir=str(tmp_path))
    await storage.set_user_balance(1, 100.0)

    result = await storage.charge_balance_once(
        1,
        0.0,
        task_id="task-zero",
        sku_id="sku-test",
        model_id="model-test",
    )

    balance = await storage.get_user_balance(1)
    assert result["status"] == "invalid_amount"
    assert balance == 100.0


@pytest.mark.asyncio
async def test_charge_balance_once_rejects_non_finite_amount(tmp_path):
    storage = JsonStorage(data_dir=str(tmp_path))
    await storage.set_user_balance(1, 100.0)

    result_nan = await storage.charge_balance_once(
        1,
        math.nan,
        task_id="task-nan",
        sku_id="sku-test",
        model_id="model-test",
    )
    result_inf = await storage.charge_balance_once(
        1,
        math.inf,
        task_id="task-inf",
        sku_id="sku-test",
        model_id="model-test",
    )

    balance = await storage.get_user_balance(1)
    assert result_nan["status"] == "invalid_amount"
    assert result_inf["status"] == "invalid_amount"
    assert balance == 100.0
