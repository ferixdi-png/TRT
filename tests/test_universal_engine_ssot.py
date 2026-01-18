import json
from unittest.mock import AsyncMock

import pytest

from app.kie_catalog import get_model_map
from app.kie_contract.payload_builder import build_kie_payload
from app.generations.universal_engine import run_generation
from app.generations.telegram_sender import send_job_result


def _build_dummy_params(model_spec):
    params = {}
    for name, schema in model_spec.schema_properties.items():
        if not schema.get("required", False):
            continue
        param_type = schema.get("type", "string")
        enum_values = schema.get("enum") or schema.get("values") or []
        if param_type == "enum" and enum_values:
            params[name] = enum_values[0]
        elif param_type == "boolean":
            params[name] = True
        elif param_type in {"number", "integer", "float"}:
            params[name] = 1
        elif param_type == "array":
            item_type = schema.get("item_type", "string")
            if item_type == "string":
                params[name] = ["https://example.com/file"]
            else:
                params[name] = ["test"]
        else:
            params[name] = "test"
    return params


def test_catalog_coverage():
    catalog = get_model_map()
    assert catalog, "Catalog must not be empty"

    for model_id, spec in catalog.items():
        assert spec.schema_properties is not None, f"{model_id} missing schema_properties"
        assert spec.schema_required is not None, f"{model_id} missing schema_required"
        assert set(spec.schema_required).issubset(set(spec.schema_properties.keys()))
        assert spec.output_media_type in {"image", "video", "audio", "voice", "text", "file"}


def test_wizard_smoke_all_models():
    catalog = get_model_map()
    for model_id, spec in catalog.items():
        params = _build_dummy_params(spec)
        payload = build_kie_payload(spec, params)
        assert payload["model"] == spec.kie_model
        assert isinstance(payload["input"], dict)


@pytest.mark.asyncio
async def test_engine_integration_by_media_type(monkeypatch):
    catalog = get_model_map()
    media_targets = {}
    for model_id, spec in catalog.items():
        media_targets.setdefault(spec.output_media_type, model_id)

    class FakeClient:
        async def create_task(self, model_id, input_data, callback_url=None):
            return {"ok": True, "taskId": "task-123"}

        async def wait_for_task(self, task_id, timeout=900, poll_interval=3):
            return {"state": "success", "resultJson": json.dumps(result_json)}

    result_json = {}

    async def run_for_media(media_type):
        model_id = media_targets.get(media_type)
        if not model_id:
            return
        spec = catalog[model_id]
        params = _build_dummy_params(spec)
        nonlocal result_json
        if media_type == "text":
            result_json = {"resultObject": "ok"}
        else:
            result_json = {"resultUrls": ["https://example.com/result"]}

        monkeypatch.setattr("app.generations.universal_engine.KIEClient", FakeClient)
        job_result = await run_generation(1, model_id, params)

        bot = AsyncMock()
        bot.send_message = AsyncMock()
        bot.send_photo = AsyncMock()
        bot.send_video = AsyncMock()
        bot.send_audio = AsyncMock()
        bot.send_voice = AsyncMock()
        bot.send_document = AsyncMock()
        bot.send_media_group = AsyncMock()

        await send_job_result(bot, 1, spec, job_result, price_rub=0.0, elapsed=1.0, user_lang="ru")

        if media_type == "text":
            assert bot.send_message.call_count >= 2
        elif media_type == "image":
            bot.send_photo.assert_called()
        elif media_type == "video":
            bot.send_video.assert_called()
        elif media_type == "audio":
            bot.send_audio.assert_called()
        elif media_type == "voice":
            bot.send_voice.assert_called()

    for media_type in ["image", "video", "audio", "voice", "text"]:
        await run_for_media(media_type)
