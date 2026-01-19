import json
from unittest.mock import AsyncMock

import pytest

from app.generations.telegram_sender import deliver_result
from app.generations.universal_engine import run_generation
from app.kie.kie_client import KIEClient
from app.kie_catalog import get_model_map


aioresponses = pytest.importorskip("aioresponses").aioresponses


@pytest.mark.asyncio
async def test_seedream_pipeline_delivers_photo(monkeypatch, test_env):
    spec = get_model_map().get("bytedance/seedream")
    if not spec:
        pytest.skip("bytedance/seedream not found in catalog")

    base_url = "https://kie.mock"
    task_id = "seedream-task"
    result_url = "https://example.com/seedream.png"

    client = KIEClient(api_key="test_api_key", base_url=base_url)
    monkeypatch.setattr("app.integrations.kie_stub.get_kie_client_or_stub", lambda: client)
    monkeypatch.setattr(
        "app.generations.universal_engine.build_kie_payload",
        lambda _spec, _params: {"input": {"prompt": "test"}},
    )

    with aioresponses() as mocked:
        mocked.post(
            f"{base_url}/api/v1/jobs/createTask",
            payload={"code": 200, "data": {"taskId": task_id}},
        )
        mocked.get(
            f"{base_url}/api/v1/jobs/recordInfo",
            payload={"code": 200, "data": {"taskId": task_id, "state": "waiting"}},
        )
        mocked.get(
            f"{base_url}/api/v1/jobs/recordInfo",
            payload={
                "code": 200,
                "data": {
                    "taskId": task_id,
                    "state": "success",
                    "resultJson": json.dumps({"resultUrls": [result_url]}),
                },
            },
        )
        mocked.get(
            result_url,
            body=b"\x89PNG\r\n\x1a\n",
            headers={"Content-Type": "image/png"},
        )

        result = await run_generation(
            user_id=1,
            model_id=spec.id,
            session_params={"prompt": "test"},
            timeout=5,
            poll_interval=0,
        )

        bot = AsyncMock()
        await deliver_result(
            bot,
            chat_id=1,
            media_type=result.media_type,
            urls=result.urls,
            text=result.text,
            model_id=spec.id,
            gen_type=spec.model_mode,
            correlation_id="corr-seedream",
        )

    bot.send_photo.assert_called_once()
