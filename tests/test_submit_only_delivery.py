import uuid

import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from app.delivery.reconciler import reconcile_pending_results
from app.generations.request_dedupe_store import get_dedupe_entry
from bot_kie import confirm_generation


def _configure_generation_monkeypatches(monkeypatch, fake_client, send_calls):
    async def fake_check_available(*_args, **_kwargs):
        return {"status": "not_free_sku"}

    async def fake_free_counter(*_args, **_kwargs):
        return ""

    def fake_normalize(_model_id, params):
        return params, []

    def fake_price(*_args, **_kwargs):
        return {"price_rub": 1.0}

    async def fake_send_result_file(*_args, **_kwargs):
        send_calls.append({"args": _args, "kwargs": _kwargs})
        return True

    async def fake_validate_result_urls(*_args, **_kwargs):
        return None

    def fake_build_payload(_spec, _params):
        return {"input": {"prompt": _params.get("prompt") or "test"}}

    monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
    monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter)
    monkeypatch.setattr(bot_kie, "_update_price_quote", fake_price)
    monkeypatch.setattr(bot_kie, "is_dry_run", lambda: False)
    monkeypatch.setattr(bot_kie, "allow_real_generation", lambda: True)
    monkeypatch.setattr(bot_kie, "_kie_readiness_state", lambda: (True, "ready"))
    monkeypatch.setattr(bot_kie, "get_is_admin", lambda _user_id: True)
    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr("app.integrations.kie_stub.get_kie_client_or_stub", lambda: fake_client)
    monkeypatch.setattr("app.generations.universal_engine.build_kie_payload", fake_build_payload)
    monkeypatch.setattr("app.delivery.reconciler.send_result_file", fake_send_result_file)
    monkeypatch.setattr("app.delivery.reconciler._validate_result_urls", fake_validate_result_urls)


class FakeKIEClient:
    def __init__(self, task_id: str, result_url: str):
        self.task_id = task_id
        self.result_url = result_url
        self.create_calls = 0
        self.status_calls = 0

    async def create_task(self, _model, _input, correlation_id=None):
        self.create_calls += 1
        return {"ok": True, "taskId": self.task_id, "correlation_id": correlation_id}

    async def get_task_status(self, task_id, **_kwargs):
        assert task_id == self.task_id
        self.status_calls += 1
        if self.status_calls == 1:
            return {"ok": True, "state": "waiting", "taskId": task_id}
        return {
            "ok": True,
            "state": "success",
            "taskId": task_id,
            "resultUrl": self.result_url,
        }


@pytest.mark.asyncio
async def test_confirm_generate_submit_only_and_delivery_worker(harness, monkeypatch):
    user_id = 9001
    task_id = f"task-submit-only-{uuid.uuid4().hex[:8]}"
    fake_client = FakeKIEClient(task_id=task_id, result_url="https://example.com/result.png")
    send_calls = []
    _configure_generation_monkeypatches(monkeypatch, fake_client, send_calls)

    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "submit-only"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
        "sku_id": "sku-submit-only",
    }

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    result = await harness.process_callback("confirm_generate", user_id=user_id)

    assert fake_client.create_calls == 1
    assert fake_client.status_calls == 0, "handler must not poll for results"

    outbox = result["outbox"]
    payload = (outbox.get("edited_messages") or outbox.get("messages"))[-1]
    assert "Задача принята" in payload["text"] or "Task accepted" in payload["text"]

    from app.storage import get_storage

    storage = get_storage()
    await reconcile_pending_results(
        harness.application.bot,
        storage,
        fake_client,
        batch_limit=10,
        pending_age_alert_seconds=9999,
        queue_tail_alert_threshold=9999,
        get_user_language=bot_kie.get_user_language,
    )
    assert fake_client.status_calls == 1
    assert not send_calls

    await reconcile_pending_results(
        harness.application.bot,
        storage,
        fake_client,
        batch_limit=10,
        pending_age_alert_seconds=9999,
        queue_tail_alert_threshold=9999,
        get_user_language=bot_kie.get_user_language,
    )

    assert fake_client.status_calls >= 2
    assert len(send_calls) == 1

    job_id = bot_kie.user_sessions[user_id]["job_id"]
    job = await storage.get_job(job_id)
    assert job
    assert (job.get("status") or "").lower() == "delivered"
    bot_kie.user_sessions.pop(user_id, None)


@pytest.mark.asyncio
async def test_dedupe_repeat_returns_same_task_and_keeps_delivery(harness, monkeypatch):
    user_id = 9002
    task_id = f"task-dedupe-{uuid.uuid4().hex[:8]}"
    fake_client = FakeKIEClient(task_id=task_id, result_url="https://example.com/dedupe.png")
    send_calls = []
    _configure_generation_monkeypatches(monkeypatch, fake_client, send_calls)
    monkeypatch.setattr(bot_kie, "prompt_summary", lambda *_args, **_kwargs: {"prompt_hash": "dedupe-hash"})

    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "dedupe"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
        "sku_id": "sku-dedupe",
    }

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    await harness.process_callback("confirm_generate", user_id=user_id)
    assert fake_client.create_calls == 1

    first_job_id = bot_kie.user_sessions[user_id]["job_id"]
    first_task_id = bot_kie.user_sessions[user_id]["task_id"]
    assert first_task_id == task_id

    await harness.process_callback("confirm_generate", user_id=user_id)

    assert fake_client.create_calls == 1, "dedupe should not create a new task"
    assert bot_kie.user_sessions[user_id]["task_id"] == task_id

    from app.storage import get_storage

    storage = get_storage()
    await reconcile_pending_results(
        harness.application.bot,
        storage,
        fake_client,
        batch_limit=10,
        pending_age_alert_seconds=9999,
        queue_tail_alert_threshold=9999,
        get_user_language=bot_kie.get_user_language,
    )
    await reconcile_pending_results(
        harness.application.bot,
        storage,
        fake_client,
        batch_limit=10,
        pending_age_alert_seconds=9999,
        queue_tail_alert_threshold=9999,
        get_user_language=bot_kie.get_user_language,
    )

    assert len(send_calls) == 1

    dedupe_entry = await get_dedupe_entry(user_id, "sora-2-text-to-video", "dedupe-hash")
    assert dedupe_entry
    assert dedupe_entry.task_id == task_id

    job = await storage.get_job(first_job_id)
    assert job
    assert (job.get("status") or "").lower() == "delivered"
    bot_kie.user_sessions.pop(user_id, None)
