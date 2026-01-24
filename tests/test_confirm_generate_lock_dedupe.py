import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from app.generations.request_dedupe_store import (
    DedupeEntry,
    get_dedupe_entry,
    set_dedupe_entry,
    set_job_task_mapping,
)
from app.generations.universal_engine import JobResult
from bot_kie import confirm_generation


@pytest.mark.asyncio
async def test_confirm_generate_dedup_joined_shows_status(harness, monkeypatch):
    user_id = 4242
    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "test", "aspect_ratio": "portrait"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
    }

    async def fake_check_available(*_args, **_kwargs):
        return {"status": "ok"}

    async def fake_free_counter(*_args, **_kwargs):
        return ""

    def fake_normalize(_model_id, params):
        return params, []

    def fake_price(*_args, **_kwargs):
        return {"price_rub": 0}

    await set_dedupe_entry(
        DedupeEntry(
            user_id=user_id,
            model_id="sora-2-text-to-video",
            prompt_hash="prompt-hash",
            job_id="job-123",
            task_id="task-123",
            status="running",
        )
    )

    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
    monkeypatch.setattr(bot_kie, "_update_price_quote", fake_price)
    monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter)
    monkeypatch.setattr(bot_kie, "prompt_summary", lambda *_args, **_kwargs: {"prompt_hash": "prompt-hash"})

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    result = await harness.process_callback("confirm_generate", user_id=user_id)

    outbox = result["outbox"]
    payload = (outbox.get("edited_messages") or outbox.get("messages"))[-1]
    assert "Генерация уже" in payload["text"] or "Generation already" in payload["text"]
    keyboard = payload["reply_markup"].inline_keyboard
    assert any(
        button.callback_data == "my_generations" for row in keyboard for button in row
    )


@pytest.mark.asyncio
async def test_confirm_generate_lock_timeout_responds(harness, monkeypatch):
    user_id = 4343
    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "test", "aspect_ratio": "portrait"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
    }

    async def fake_check_available(*_args, **_kwargs):
        return {"status": "ok"}

    async def fake_free_counter(*_args, **_kwargs):
        return ""

    def fake_normalize(_model_id, params):
        return params, []

    def fake_price(*_args, **_kwargs):
        return {"price_rub": 0}

    class FakeLockResult:
        def __init__(self):
            self.wait_ms_total = 12000
            self.attempts = 3
            self.ttl_seconds = 180
            self.key = "gen"

        def __bool__(self):
            return False

    class FakeLock:
        async def __aenter__(self):
            return FakeLockResult()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
    monkeypatch.setattr(bot_kie, "_update_price_quote", fake_price)
    monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter)
    monkeypatch.setattr(bot_kie, "prompt_summary", lambda *_args, **_kwargs: {"prompt_hash": "prompt-hash-2"})
    monkeypatch.setattr("app.utils.distributed_lock.distributed_lock", lambda *args, **kwargs: FakeLock())

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    result = await harness.process_callback("confirm_generate", user_id=user_id)

    outbox = result["outbox"]
    payload = (outbox.get("edited_messages") or outbox.get("messages"))[-1]
    assert "параллельная" in payload["text"].lower() or "parallel" in payload["text"].lower()
    keyboard = payload["reply_markup"].inline_keyboard
    assert any(
        button.callback_data == "my_generations" for row in keyboard for button in row
    )


@pytest.mark.asyncio
async def test_confirm_generate_resolves_task_id_from_job_mapping(harness, monkeypatch):
    user_id = 4444
    prompt_hash = "prompt-hash-map"
    job_id = "job-map-4444"
    task_id = "task-map-4444"
    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "mapping"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
    }

    async def fake_check_available(*_args, **_kwargs):
        return {"status": "ok"}

    async def fake_free_counter(*_args, **_kwargs):
        return ""

    def fake_normalize(_model_id, params):
        return params, []

    def fake_price(*_args, **_kwargs):
        return {"price_rub": 0}

    async def fail_run_generation(*_args, **_kwargs):
        raise AssertionError("run_generation should not be called on valid dedupe join")

    await set_dedupe_entry(
        DedupeEntry(
            user_id=user_id,
            model_id="sora-2-text-to-video",
            prompt_hash=prompt_hash,
            job_id=job_id,
            task_id=None,
            status="pending",
        )
    )
    await set_job_task_mapping(job_id, task_id)

    monkeypatch.setattr(bot_kie, "DEDUPE_TASK_RESOLUTION_ATTEMPTS", 1)
    monkeypatch.setattr(bot_kie, "DEDUPE_TASK_RESOLUTION_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("app.generations.universal_engine.run_generation", fail_run_generation)
    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
    monkeypatch.setattr(bot_kie, "_update_price_quote", fake_price)
    monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter)
    monkeypatch.setattr(bot_kie, "prompt_summary", lambda *_args, **_kwargs: {"prompt_hash": prompt_hash})

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    result = await harness.process_callback("confirm_generate", user_id=user_id)

    payload = (result["outbox"].get("edited_messages") or result["outbox"].get("messages"))[-1]
    assert task_id in payload["text"]
    entry = await get_dedupe_entry(user_id, "sora-2-text-to-video", prompt_hash)
    assert entry and entry.task_id == task_id


@pytest.mark.asyncio
async def test_confirm_generate_broken_dedupe_restarts_generation(harness, monkeypatch):
    user_id = 4545
    prompt_hash = "prompt-hash-broken"
    dangling_job_id = "job-dangling-4545"
    new_task_id = "task-new-4545"
    bot_kie.user_sessions[user_id] = {
        "model_id": "sora-2-text-to-video",
        "params": {"prompt": "broken"},
        "model_info": {"name": "Sora 2"},
        "gen_type": "video",
    }

    async def fake_check_available(*_args, **_kwargs):
        return {"status": "ok"}

    async def fake_free_counter(*_args, **_kwargs):
        return ""

    def fake_normalize(_model_id, params):
        return params, []

    def fake_price(*_args, **_kwargs):
        return {"price_rub": 0}

    async def fake_send_result_file(*_args, **_kwargs):
        return True

    async def fake_run_generation(*_args, **kwargs):
        on_task_created = kwargs.get("on_task_created")
        if on_task_created:
            await on_task_created(new_task_id)
        return JobResult(
            task_id=new_task_id,
            state="succeeded",
            media_type="image",
            urls=["https://example.com/result.png"],
            text=None,
            raw={},
        )

    async def fake_resolve_task_id_from_job(_job_id: str):
        return None

    await set_dedupe_entry(
        DedupeEntry(
            user_id=user_id,
            model_id="sora-2-text-to-video",
            prompt_hash=prompt_hash,
            job_id=dangling_job_id,
            task_id=None,
            status="pending",
        )
    )

    monkeypatch.setattr(bot_kie, "DEDUPE_TASK_RESOLUTION_ATTEMPTS", 1)
    monkeypatch.setattr(bot_kie, "DEDUPE_TASK_RESOLUTION_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(bot_kie, "_resolve_task_id_from_job", fake_resolve_task_id_from_job)
    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)
    monkeypatch.setattr(bot_kie, "is_dry_run", lambda: False)
    monkeypatch.setattr(bot_kie, "allow_real_generation", lambda: True)
    monkeypatch.setattr("app.generations.telegram_sender.send_result_file", fake_send_result_file)
    monkeypatch.setattr("kie_input_adapter.normalize_for_generation", fake_normalize)
    monkeypatch.setattr(bot_kie, "check_free_generation_available", fake_check_available)
    monkeypatch.setattr(bot_kie, "_update_price_quote", fake_price)
    monkeypatch.setattr(bot_kie, "get_free_counter_line", fake_free_counter)
    monkeypatch.setattr(bot_kie, "prompt_summary", lambda *_args, **_kwargs: {"prompt_hash": prompt_hash})

    harness.add_handler(CallbackQueryHandler(confirm_generation, pattern="^confirm_generate$"))
    await harness.process_callback("confirm_generate", user_id=user_id)

    entry = await get_dedupe_entry(user_id, "sora-2-text-to-video", prompt_hash)
    assert entry and entry.task_id == new_task_id
    assert entry.job_id and entry.job_id != dangling_job_id
