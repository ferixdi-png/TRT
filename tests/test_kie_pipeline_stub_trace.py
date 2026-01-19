import os
from unittest.mock import AsyncMock

from app.generations.universal_engine import run_generation
from app.generations.telegram_sender import send_job_result
from app.kie_catalog import get_model_map


def test_kie_pipeline_stub_trace(monkeypatch, test_env):
    os.environ["KIE_STUB"] = "1"

    trace_calls = []

    def _collector(level, correlation_id, **fields):
        trace_calls.append({"correlation_id": correlation_id, "fields": fields})

    monkeypatch.setattr("app.observability.trace.trace_event", _collector)
    monkeypatch.setattr("app.observability.no_silence_guard.trace_event", _collector)

    # Patch payload builder to avoid strict validation
    monkeypatch.setattr(
        "app.generations.universal_engine.build_kie_payload",
        lambda spec, params: {"input": {"prompt": "test"}},
    )

    model_id = next(iter(get_model_map().keys()))
    correlation_id = "corr-test-1-1-abc123"

    job_result = AsyncMock()

    import asyncio

    job_result = asyncio.run(run_generation(1, model_id, {"prompt": "test"}, correlation_id=correlation_id))

    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_video = AsyncMock()
    bot.send_audio = AsyncMock()
    bot.send_voice = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_media_group = AsyncMock()

    asyncio.run(
        send_job_result(
            bot,
            1,
            get_model_map()[model_id],
            job_result,
            price_rub=0.0,
            elapsed=1.0,
            user_lang="ru",
            correlation_id=correlation_id,
        )
    )

    stages = {call["fields"].get("stage") for call in trace_calls}
    assert "KIE_CREATE" in stages
    assert "KIE_POLL" in stages
    assert "TG_DELIVER" in stages
