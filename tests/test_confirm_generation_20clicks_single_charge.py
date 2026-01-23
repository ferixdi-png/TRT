import asyncio

import pytest

from app.pricing.price_resolver import resolve_price_quote
from app.storage.factory import get_storage
from app.generations.universal_engine import JobResult
from tests.webhook_test_utils import build_session_payload, select_paid_model


@pytest.mark.asyncio
async def test_confirm_generation_20clicks_single_charge(webhook_harness, monkeypatch):
    selection = select_paid_model()
    assert selection is not None, "No paid model found for test."

    session, params = build_session_payload(selection)
    user_id = 4242
    webhook_harness.session_store.set(user_id, session)

    price_quote = resolve_price_quote(
        model_id=selection.model_id,
        mode_index=0,
        gen_type=session.get("gen_type"),
        selected_params=params,
    )
    assert price_quote is not None, "Pricing unavailable for selected model."
    price = float(price_quote.price_rub)

    storage = get_storage()
    await storage.set_user_balance(user_id, price * 5)

    submit_calls = {"count": 0}

    async def fake_run_generation(*args, **kwargs):
        submit_calls["count"] += 1
        return JobResult(
            task_id="task-fixed-123",
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

    tasks = []
    for index in range(20):
        tasks.append(
            webhook_harness.send_callback(
                user_id=user_id,
                callback_data="confirm_generate",
                update_id=100 + index,
                message_id=10,
                request_id=f"corr-20clicks-{index}",
            )
        )
    await asyncio.gather(*tasks)

    balance_after = await storage.get_user_balance(user_id)
    assert submit_calls["count"] == 1
    assert balance_after == pytest.approx(price * 4)
    primary = getattr(storage, "_primary", None)
    history = await primary.read_json_file("generations_history.json", default={})
    assert len(history.get(str(user_id), [])) == 1
    assert any(
        "Генерация уже запускается" in message.get("text", "")
        for message in webhook_harness.outbox.messages + webhook_harness.outbox.edited_messages
    )
