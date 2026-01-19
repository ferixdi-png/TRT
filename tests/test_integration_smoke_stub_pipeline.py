import json
import pytest

from app.generations.telegram_sender import deliver_result
from app.generations.universal_engine import run_generation
from app.generations import media_pipeline
from app.integrations.kie_stub import KIEStub
from app.kie_catalog import get_model_map


def _generate_minimal_params(schema):
    params = {}
    for name, spec in schema.items():
        if not spec.get("required", False):
            continue
        param_type = spec.get("type", "string")
        if name in {"prompt", "text"}:
            params[name] = "Test prompt"
        elif param_type == "boolean":
            params[name] = False
        elif param_type in {"number", "integer", "float"}:
            params[name] = spec.get("min", 1)
        elif param_type == "enum":
            values = spec.get("values") or spec.get("enum") or []
            params[name] = values[0] if values else "default"
        elif param_type == "array":
            params[name] = ["https://example.com/test.png"]
        elif "url" in name:
            params[name] = "https://example.com/test.png"
        else:
            params[name] = "test_value"
    return params


class DummyBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id=None, **kwargs):
        self.calls.append(("send_message", chat_id, kwargs))

    async def send_photo(self, chat_id=None, **kwargs):
        self.calls.append(("send_photo", chat_id, kwargs))

    async def send_document(self, chat_id=None, **kwargs):
        self.calls.append(("send_document", chat_id, kwargs))


@pytest.mark.asyncio
async def test_integration_smoke_stub_pipeline(monkeypatch, test_env):
    monkeypatch.setenv("KIE_STUB", "1")

    spec = next(
        (model for model in get_model_map().values() if model.output_media_type == "image"),
        None,
    )
    if not spec:
        pytest.skip("No image model available in catalog")

    async def fast_simulate(self, task_id: str):
        task = self._tasks[task_id]
        task["state"] = "success"
        result_urls = [f"https://example.com/generated/{task_id}.png"]
        task["result_urls"] = result_urls
        task["resultJson"] = json.dumps({"resultUrls": result_urls})
        task["resultText"] = None

    monkeypatch.setattr(KIEStub, "_simulate_processing", fast_simulate)

    async def fake_download(session, url, retries=2):
        return b"\x89PNG\r\n\x1a\n", "image/png", 8

    monkeypatch.setattr(media_pipeline, "_download_with_retries", fake_download)

    params = _generate_minimal_params(spec.schema_properties or {})

    result = await run_generation(
        user_id=1,
        model_id=spec.id,
        session_params=params,
        timeout=5,
        poll_interval=0,
    )

    bot = DummyBot()
    await deliver_result(
        bot,
        chat_id=1,
        media_type=result.media_type,
        urls=result.urls,
        text="stub",
        correlation_id="corr-smoke",
    )

    assert bot.calls
    assert bot.calls[0][0] in {"send_photo", "send_document"}
