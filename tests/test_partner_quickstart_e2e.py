import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler

from app.admin.router import show_admin_root
from app.generations.universal_engine import JobResult
from app.services.history_service import get_recent
from app.storage.factory import get_storage, reset_storage
from bot_kie import button_callback, start
from tests.webhook_test_utils import build_session_payload, select_free_model, select_paid_model


def _last_payload(outbox: dict) -> dict:
    edited = outbox.get("edited_messages", [])
    messages = outbox.get("messages", [])
    return edited[-1] if edited else messages[-1]


@pytest.mark.asyncio
async def test_e2e_main_menu_click_through(harness):
    user_id = 34567
    harness.add_handler(CommandHandler("start", start))
    harness.add_handler(CallbackQueryHandler(button_callback))

    result = await harness.process_command("/start", user_id=user_id)
    assert result["success"]

    for callback in ["check_balance", "show_models", "all_models", "help_menu", "support_contact"]:
        result = await harness.process_callback(callback, user_id=user_id)
        assert result["success"]
        payload = _last_payload(result["outbox"])
        assert payload.get("text")


@pytest.mark.asyncio
async def test_e2e_prompt_generation_history(webhook_harness, monkeypatch):
    selection = select_free_model() or select_paid_model()
    assert selection is not None, "No model found for quickstart e2e."

    session, _ = build_session_payload(selection)
    user_id = 6061
    webhook_harness.session_store.set(user_id, session)

    if not selection.sku.is_free_sku:
        storage = get_storage()
        await storage.set_user_balance(user_id, 100.0)

    async def fake_run_generation(*_args, **_kwargs):
        return JobResult(
            task_id="quickstart-task-1",
            state="completed",
            media_type="text",
            urls=[],
            text="OK",
            raw={},
        )

    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

    response = await webhook_harness.send_callback(
        user_id=user_id,
        callback_data="confirm_generate",
        update_id=700,
        message_id=7,
        request_id="corr-quickstart-1",
    )
    assert response.status == 200

    storage_after = get_storage()
    recent = await get_recent(storage_after, user_id=user_id, limit=5)
    assert recent

    reset_storage()


@pytest.mark.asyncio
async def test_e2e_admin_diagnostics(harness):
    admin_id = 12345
    harness.add_handler(CommandHandler("admin", show_admin_root))

    result = await harness.process_command("/admin", user_id=admin_id)
    assert result["success"]
    payload = _last_payload(result["outbox"])
    text = payload.get("text", "")
    assert "BOT_INSTANCE_ID" in text
    assert "Tenant scope" in text
    assert "DB:" in text
    assert "Redis:" in text
