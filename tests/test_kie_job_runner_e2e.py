import json

import pytest

aioresponses = pytest.importorskip("aioresponses").aioresponses

from app.generations.universal_engine import run_generation
from app.kie.kie_client import KIEClient
from app.kie_catalog import get_model_map


def _pick_model(predicate, label: str):
    for spec in get_model_map().values():
        if predicate(spec):
            return spec
    pytest.skip(f"No model found for {label}")


async def _run_generation_with_mock(
    monkeypatch,
    *,
    spec,
    result_json,
    media_type: str,
):
    base_url = "https://kie.mock"
    task_id = "task-123"
    client = KIEClient(api_key="test_api_key", base_url=base_url)
    monkeypatch.setattr("app.integrations.kie_stub.get_kie_client_or_stub", lambda: client)
    monkeypatch.setattr(
        "app.generations.universal_engine.build_kie_payload",
        lambda _spec, _params: {"input": {"prompt": "test"}},
    )
    record_url = f"{base_url}/api/v1/jobs/recordInfo"
    create_url = f"{base_url}/api/v1/jobs/createTask"
    with aioresponses() as mocked:
        mocked.post(create_url, payload={"code": 200, "data": {"taskId": task_id}})
        mocked.get(record_url, payload={"code": 200, "data": {"taskId": task_id, "state": "waiting"}})
        mocked.get(
            record_url,
            payload={
                "code": 200,
                "data": {"taskId": task_id, "state": "success", "resultJson": json.dumps(result_json)},
            },
        )
        result = await run_generation(
            user_id=1,
            model_id=spec.id,
            session_params={"prompt": "test"},
            timeout=5,
            poll_interval=0,
        )

    assert result.media_type == media_type
    return result


@pytest.mark.asyncio
async def test_kie_e2e_image_generation(monkeypatch, test_env):
    spec = _pick_model(lambda model: model.output_media_type == "image", "image")
    url = "https://example.com/image.png"
    result = await _run_generation_with_mock(
        monkeypatch,
        spec=spec,
        result_json={"resultUrls": [url]},
        media_type="image",
    )
    assert result.urls == [url]


@pytest.mark.asyncio
async def test_kie_e2e_video_generation(monkeypatch, test_env):
    spec = _pick_model(lambda model: model.output_media_type == "video", "video")
    url = "https://example.com/video.mp4"
    result = await _run_generation_with_mock(
        monkeypatch,
        spec=spec,
        result_json={"resultUrls": [url]},
        media_type="video",
    )
    assert result.urls == [url]


@pytest.mark.asyncio
async def test_kie_e2e_audio_generation(monkeypatch, test_env):
    spec = _pick_model(lambda model: model.output_media_type in {"audio", "voice"}, "audio")
    url = "https://example.com/audio.mp3"
    result = await _run_generation_with_mock(
        monkeypatch,
        spec=spec,
        result_json={"resultUrls": [url]},
        media_type=spec.output_media_type,
    )
    assert result.urls == [url]


@pytest.mark.asyncio
async def test_kie_e2e_stt_generation(monkeypatch, test_env):
    spec = _pick_model(
        lambda model: model.output_media_type == "text" and "speech" in model.model_type,
        "stt",
    )
    result = await _run_generation_with_mock(
        monkeypatch,
        spec=spec,
        result_json={"resultObject": "Hello from STT"},
        media_type="text",
    )
    assert result.text == "Hello from STT"


@pytest.mark.asyncio
async def test_kie_e2e_photo_enhancement(monkeypatch, test_env):
    spec = _pick_model(
        lambda model: model.model_type in {"image_edit", "image_to_image", "upscale"},
        "photo enhancement",
    )
    url = "https://example.com/enhanced.png"
    result = await _run_generation_with_mock(
        monkeypatch,
        spec=spec,
        result_json={"resultUrls": [url]},
        media_type=spec.output_media_type or "image",
    )
    assert result.urls == [url]
