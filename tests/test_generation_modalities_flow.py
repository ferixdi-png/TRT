from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.generations.universal_engine import JobResult
from app.kie_catalog import get_model_map
from bot_kie import ADMIN_ID, button_callback, confirm_generation, user_sessions
from tests.ptb_harness import PTBHarness


def _pick_model(predicate, label: str):
    for spec in get_model_map().values():
        if predicate(spec):
            return spec
    pytest.skip(f"No model found for {label}")


def _build_dummy_params(model_spec):
    params = {}
    for name, schema in model_spec.schema_properties.items():
        if not schema.get("required", False):
            continue
        param_type = schema.get("type", "string")
        enum_values = schema.get("enum") or schema.get("values") or []
        if isinstance(enum_values, dict):
            enum_values = list(enum_values.values())
        if isinstance(enum_values, list) and enum_values and isinstance(enum_values[0], dict):
            enum_values = [value.get("value") or value.get("id") or value.get("name") for value in enum_values]
            enum_values = [value for value in enum_values if value is not None]
        if param_type == "enum" and enum_values:
            params[name] = enum_values[0]
        elif param_type == "boolean":
            params[name] = True
        elif param_type in {"number", "integer", "float"}:
            params[name] = 1
        elif param_type == "array":
            params[name] = ["https://example.com/file"]
        else:
            params[name] = "test"
    return params


async def _run_flow(monkeypatch, harness, spec, job_result, expected_method):
    user_id = ADMIN_ID
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    monkeypatch.setattr(
        "kie_input_adapter.normalize_for_generation",
        lambda _model_id, params: (params, []),
    )

    async def fake_run_generation(*_args, **_kwargs):
        return job_result

    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

    update_select = harness.create_mock_update_callback(f"select_model:{spec.id}", user_id=user_id)
    await button_callback(update_select, context)

    session = user_sessions[user_id]
    session["params"] = _build_dummy_params(spec)
    session["waiting_for"] = None
    session["current_param"] = None

    update_confirm = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
    await confirm_generation(update_confirm, context)

    assert getattr(harness.application.bot, expected_method).called

    user_sessions.pop(user_id, None)


@pytest.mark.asyncio
async def test_generation_flow_image(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        spec = _pick_model(lambda model: model.output_media_type == "image", "image")
        job_result = JobResult(
            task_id="task-1",
            state="success",
            media_type="image",
            urls=["https://example.com/image.png"],
            text=None,
            raw={"elapsed": 0.1},
        )
        await _run_flow(monkeypatch, harness, spec, job_result, "send_photo")
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_generation_flow_video(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        spec = _pick_model(lambda model: model.output_media_type == "video", "video")
        job_result = JobResult(
            task_id="task-2",
            state="success",
            media_type="video",
            urls=["https://example.com/video.mp4"],
            text=None,
            raw={"elapsed": 0.1},
        )
        await _run_flow(monkeypatch, harness, spec, job_result, "send_video")
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_generation_flow_audio(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        spec = _pick_model(lambda model: model.output_media_type == "audio", "audio")
        media_type = spec.output_media_type or "audio"
        job_result = JobResult(
            task_id="task-3",
            state="success",
            media_type=media_type,
            urls=["https://example.com/audio.ogg"],
            text=None,
            raw={"elapsed": 0.1},
        )
        await _run_flow(monkeypatch, harness, spec, job_result, "send_audio")
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_generation_flow_text(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        spec = _pick_model(
            lambda model: model.output_media_type == "text" and "speech" not in model.model_type,
            "text",
        )
        job_result = JobResult(
            task_id="task-4",
            state="success",
            media_type="text",
            urls=[],
            text="Generated text",
            raw={"elapsed": 0.1},
        )
        await _run_flow(monkeypatch, harness, spec, job_result, "send_message")
    finally:
        await harness.teardown()


@pytest.mark.asyncio
@pytest.mark.xfail(reason="speech_to_text model not always available in catalog")
async def test_generation_flow_speech_to_text(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        spec = _pick_model(
            lambda model: model.output_media_type == "text" and "speech_to_text" in model.model_type,
            "speech-to-text",
        )
        job_result = JobResult(
            task_id="task-5",
            state="success",
            media_type="text",
            urls=[],
            text="Transcribed text",
            raw={"elapsed": 0.1},
        )
        await _run_flow(monkeypatch, harness, spec, job_result, "send_message")
    finally:
        await harness.teardown()
