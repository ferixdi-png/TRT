import pytest

from app.services.history_service import get_recent
from app.storage.factory import get_storage, reset_storage
from app.generations.universal_engine import JobResult
from app.pricing import free_policy
from tests.webhook_test_utils import build_session_payload, select_free_model


@pytest.mark.asyncio
async def test_free_limits_and_history_e2e(webhook_harness, monkeypatch):
    selection = select_free_model()
    assert selection is not None, "No free model found for test."

    monkeypatch.setattr(free_policy, "get_free_daily_limit", lambda: 1)

    session, _ = build_session_payload(selection)
    user_id = 6060
    webhook_harness.session_store.set(user_id, session)

    async def fake_run_generation(*args, **kwargs):
        return JobResult(
            task_id="free-task-1",
            state="completed",
            media_type="text",
            urls=[],
            text="FREE_OK",
            raw={},
        )

    monkeypatch.setattr(
        "app.generations.universal_engine.run_generation",
        fake_run_generation,
    )

    response = await webhook_harness.send_callback(
        user_id=user_id,
        callback_data="confirm_generate",
        update_id=600,
        message_id=6,
        request_id="corr-free-1",
    )
    assert response.status == 200

    storage = get_storage()
    used_today = await storage.get_user_free_generations_today(user_id)
    assert used_today == 1

    reset_storage()
    storage_after_restart = get_storage()
    used_after = await storage_after_restart.get_user_free_generations_today(user_id)
    assert used_after == 1

    recent = await get_recent(storage_after_restart, user_id=user_id, limit=5)
    assert recent

    webhook_harness.session_store.set(user_id, session)
    response_second = await webhook_harness.send_callback(
        user_id=user_id,
        callback_data="confirm_generate",
        update_id=601,
        message_id=6,
        request_id="corr-free-2",
    )
    assert response_second.status == 200
    combined = webhook_harness.outbox.messages + webhook_harness.outbox.edited_messages
    assert any("лимит бесплатных генераций исчерпан" in message.get("text", "").lower() for message in combined)
    last = combined[-1]
    reply_markup = last.get("reply_markup")
    assert reply_markup is not None
    keyboard = getattr(reply_markup, "inline_keyboard", [])
    labels = [button.text for row in keyboard for button in row]
    assert any("Главное меню" in label for label in labels)
