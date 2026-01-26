import json
from unittest.mock import AsyncMock

import pytest

from app.kie_catalog import get_model_map
from app.kie_contract.payload_builder import build_kie_payload
from app.generations.universal_engine import parse_record_info
from app.generations.telegram_sender import send_job_result
from app.generations import media_pipeline
from bot_kie import _determine_primary_input


def _build_dummy_params(model_spec):
    params = {}
    required_fields = set(model_spec.schema_required or [])
    for name, schema in model_spec.schema_properties.items():
        if not schema.get("required", False) and name not in required_fields:
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
            item_type = schema.get("item_type", "string")
            if item_type == "string":
                params[name] = ["https://example.com/file"]
            else:
                params[name] = ["test"]
        else:
            params[name] = "test"
    return params


def _expected_primary_input(model_mode: str) -> str:
    text_modes = {"text_to_image", "text_to_video", "text_to_audio", "text_to_speech", "text"}
    image_modes = {"image_to_image", "image_edit", "image_to_video", "outpaint", "upscale", "lip_sync"}
    video_modes = {"video_editing", "video_upscale"}
    audio_modes = {"speech_to_text", "audio_to_audio", "speech_to_video"}
    if model_mode in text_modes:
        return "prompt"
    if model_mode in image_modes:
        return "image"
    if model_mode in audio_modes:
        return "audio"
    if model_mode in video_modes:
        return "video"
    pytest.fail(f"Unknown model_mode for input contract: {model_mode}")


def test_all_models_require_correct_primary_input():
    catalog = get_model_map()
    for model_id, spec in catalog.items():
        model_mode = spec.model_mode or spec.model_type or ""
        expected_type = _expected_primary_input(model_mode)
        primary = _determine_primary_input({"model_mode": model_mode, "model_type": spec.model_type}, spec.schema_properties)
        assert primary is not None, f"{model_id} missing primary input"
        assert primary["type"] == expected_type, f"{model_id} expected {expected_type}, got {primary}"


def test_payload_builder_includes_required_fields():
    catalog = get_model_map()
    media_aliases = {
        "image_input": {"image_url", "image_urls", "image", "image_base64"},
        "audio_input": {"audio_url", "audio"},
        "video_input": {"video_url", "video_urls", "video"},
    }
    for model_id, spec in catalog.items():
        params = _build_dummy_params(spec)
        payload = build_kie_payload(spec, params)
        for required_field in spec.schema_required:
            if required_field not in payload["input"]:
                aliases = media_aliases.get(required_field, set())
                if aliases and any(alias in payload["input"] for alias in aliases):
                    continue
            assert required_field in payload["input"], f"{model_id} missing {required_field} in payload"


@pytest.mark.asyncio
async def test_telegram_sender_selects_correct_method(monkeypatch):
    catalog = get_model_map()
    method_map = {
        "image": "send_photo",
        "video": "send_video",
        "audio": "send_audio",
        "text": "send_message",
        "document": "send_document",
    }

    async def fake_download(session, url, **kwargs):
        if url.endswith(".png"):
            return b"\x89PNG\r\n\x1a\nfake", "image/png", 16
        if url.endswith(".mp4"):
            return b"\x00\x00\x00\x18ftypisom", "video/mp4", 16
        if url.endswith(".mp3"):
            return b"ID3fake", "audio/mpeg", 16
        if url.endswith(".ogg"):
            return b"OggSfake", "audio/ogg", 16
        return b"PK\x03\x04fake", "application/zip", 16

    monkeypatch.setattr(media_pipeline, "_download_with_retries", fake_download)

    for model_id, spec in catalog.items():
        media_kind = spec.output_media_type or "document"
        record = {"taskId": "task-123", "state": "success"}
        if media_kind == "text":
            record["resultJson"] = json.dumps({"resultText": "ok"})
        else:
            ext = {
                "image": "png",
                "video": "mp4",
                "audio": "mp3",
            }.get(media_kind, "bin")
            record["resultUrls"] = [f"https://example.com/file.{ext}"]

        job_result = parse_record_info(record, media_kind, model_id)

        bot = AsyncMock()
        bot.send_message = AsyncMock()
        bot.send_photo = AsyncMock()
        bot.send_video = AsyncMock()
        bot.send_audio = AsyncMock()
        bot.send_voice = AsyncMock()
        bot.send_document = AsyncMock()
        bot.send_media_group = AsyncMock()

        await send_job_result(bot, 1, spec, job_result, price_rub=0, elapsed=1, user_lang="ru")

        expected_method = method_map.get(media_kind, "send_document")
        if expected_method == "send_message":
            assert bot.send_message.call_count >= 2
        else:
            send_fn = getattr(bot, expected_method)
            assert send_fn.call_count >= 1, f"{model_id} expected {expected_method}"
