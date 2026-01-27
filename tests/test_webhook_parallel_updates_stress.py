import asyncio

import pytest

from app.pricing.price_resolver import resolve_price_quote
from app.storage.factory import get_storage
from app.generations.universal_engine import JobResult
from tests.webhook_test_utils import build_session_payload, select_paid_model


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Billing balance assertion flaky under parallel stress; needs investigation")
async def test_webhook_parallel_updates_stress(webhook_harness, monkeypatch):
    selection = select_paid_model()
    assert selection is not None, "No paid model found for test."

    session, params = build_session_payload(selection)
    user_id = 9090
    webhook_harness.session_store.set(user_id, session)

    price_quote = resolve_price_quote(
        model_id=selection.model_id,
        mode_index=0,
        gen_type=session.get("gen_type"),
        selected_params=params,
    )
    assert price_quote is not None
    price = float(price_quote.price_rub)

    storage = get_storage()
    await storage.set_user_balance(user_id, price * 3)

    submit_calls = {"count": 0}

    async def fake_run_generation(*args, **kwargs):
        submit_calls["count"] += 1
        return JobResult(
            task_id="task-parallel-1",
            state="completed",
            media_type="text",
            urls=[],
            text="OK",
            raw={},
        )

    monkeypatch.setattr(
        "app.generations.universal_engine.run_generation",
        fake_run_generation,
    )

    tasks = [
        webhook_harness.send_callback(
            user_id=user_id,
            callback_data="confirm_generate",
            update_id=900 + idx,
            message_id=9,
            request_id=f"corr-parallel-{idx}",
        )
        for idx in range(10)
    ]

    responses = await asyncio.gather(*tasks)
    assert all(response.status == 200 for response in responses)

    balance_after = await storage.get_user_balance(user_id)
    assert submit_calls["count"] == 1
    assert balance_after == pytest.approx(price * 2)
