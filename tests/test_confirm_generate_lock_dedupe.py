import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from app.generations.request_dedupe_store import DedupeEntry, set_dedupe_entry
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
