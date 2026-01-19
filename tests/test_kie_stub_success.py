import json

import pytest

from app.generations.universal_engine import run_generation
from app.integrations.kie_stub import KIEStub
from app.kie_catalog import get_model_map


def _pick_model(predicate, label: str):
    for spec in get_model_map().values():
        if predicate(spec):
            return spec
    pytest.skip(f"No model found for {label}")


@pytest.mark.asyncio
async def test_stub_path_success_for_image_text_video(monkeypatch, test_env):
    stub = KIEStub()

    async def fast_simulate(self, task_id):
        if task_id not in self._tasks:
            return
        task = self._tasks[task_id]
        model_id_lower = task["model_id"].lower()
        result_urls = []
        result_text = None
        if "image" in model_id_lower:
            result_urls = [f"https://example.com/generated/image_{task_id}.png"]
        elif "video" in model_id_lower:
            result_urls = [f"https://example.com/generated/video_{task_id}.mp4"]
        elif "audio" in model_id_lower:
            result_urls = [f"https://example.com/generated/audio_{task_id}.mp3"]
        else:
            result_text = f"Stub result for task {task_id}"
        task["state"] = "success"
        task["result_urls"] = result_urls
        task["resultText"] = result_text
        task["resultJson"] = json.dumps(
            {
                "resultUrls": result_urls,
                "resultText": result_text,
                "resultObject": result_text,
            }
        )

    monkeypatch.setattr(KIEStub, "_simulate_processing", fast_simulate)
    monkeypatch.setattr("app.integrations.kie_stub.get_kie_client_or_stub", lambda: stub)
    monkeypatch.setattr(
        "app.generations.universal_engine.build_kie_payload",
        lambda _spec, _params: {"input": {"prompt": "test"}},
    )

    image_spec = _pick_model(lambda model: model.output_media_type == "image", "image")
    video_spec = _pick_model(lambda model: model.output_media_type == "video", "video")
    text_spec = _pick_model(lambda model: model.output_media_type == "text", "text")

    image_result = await run_generation(1, image_spec.id, {"prompt": "test"}, poll_interval=0)
    assert image_result.state == "success"
    assert image_result.urls

    video_result = await run_generation(1, video_spec.id, {"prompt": "test"}, poll_interval=0)
    assert video_result.state == "success"
    assert video_result.urls

    text_result = await run_generation(1, text_spec.id, {"prompt": "test"}, poll_interval=0)
    assert text_result.state == "success"
    assert text_result.text
