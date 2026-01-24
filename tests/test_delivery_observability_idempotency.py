import json
from types import SimpleNamespace

import pytest

from app.delivery import reconciler as delivery_reconciler
from app.generations.universal_engine import JobResult
from app.observability.correlation_store import reset_correlation_store
from app.storage.factory import get_storage, reset_storage


def _structured_payloads(caplog):
    payloads = []
    for record in caplog.records:
        if record.name != "app.observability.structured_logs":
            continue
        message = record.getMessage()
        if "STRUCTURED_LOG " not in message:
            continue
        payloads.append(json.loads(message.split("STRUCTURED_LOG ", 1)[1]))
    return payloads


class DummyBot:
    def __init__(self) -> None:
        self.calls = []

    async def send_document(self, chat_id: int, **payload):
        self.calls.append(("send_document", chat_id, payload))
        return {"ok": True}

    async def send_message(self, chat_id: int, text: str, **payload):
        self.calls.append(("send_message", chat_id, {"text": text, **payload}))
        return {"ok": True}


async def _setup_storage(monkeypatch, tmp_path, *, tenant: str):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOT_INSTANCE_ID", tenant)
    reset_storage()
    reset_correlation_store()
    return get_storage()


@pytest.mark.asyncio
async def test_delivery_logs_have_task_and_job_ids(monkeypatch, tmp_path, caplog):
    storage = await _setup_storage(monkeypatch, tmp_path, tenant="tenant-happy")
    caplog.set_level("INFO", logger="app.observability.structured_logs")

    user_id = 1010
    job_id = "job-happy-1010"
    task_id = "task-happy-1010"
    request_id = "corr-happy-1010"
    url = "https://example.com/result.png"

    await storage.add_generation_job(
        user_id=user_id,
        model_id="demo-model",
        model_name="Demo",
        params={"prompt": "test"},
        price=0.0,
        task_id=task_id,
        status="succeeded",
        job_id=job_id,
        request_id=request_id,
        correlation_id=request_id,
        prompt="test",
        prompt_hash="hash-happy",
        chat_id=user_id,
        message_id=55,
    )
    job = await storage.get_job(job_id)
    assert job is not None

    async def fake_parse_record_info(*_args, **_kwargs):
        return JobResult(
            task_id=task_id,
            state="success",
            media_type="image",
            urls=[url],
            text="done",
            raw={},
        )

    async def fake_validate_result_urls(*_args, **_kwargs):
        return None

    async def fake_resolve(*_args, **_kwargs):
        return "send_document", {"document": "file-id"}

    monkeypatch.setattr(delivery_reconciler, "parse_record_info", fake_parse_record_info)
    monkeypatch.setattr(delivery_reconciler, "_validate_result_urls", fake_validate_result_urls)
    monkeypatch.setattr(delivery_reconciler, "get_model", lambda _model_id: SimpleNamespace(output_media_type="image", model_mode="image", name="Demo"))
    monkeypatch.setattr("app.generations.telegram_sender.resolve_and_prepare_telegram_payload", fake_resolve)

    bot = DummyBot()
    delivered = await delivery_reconciler.deliver_job_result(
        bot,
        storage,
        job=job,
        status_record={"state": "success", "taskId": task_id},
        notify_user=False,
        source="test_happy_path",
    )
    assert delivered is True

    payloads = _structured_payloads(caplog)
    relevant = [
        payload
        for payload in payloads
        if payload.get("action") in {"TG_DELIVER", "RESULT_DELIVERED", "DELIVERY_SEND_OK"}
    ]
    assert relevant, "Expected delivery structured logs"
    assert all(payload.get("task_id") for payload in relevant)
    assert all(payload.get("job_id") for payload in relevant)
    assert all(payload.get("outcome") != "partial" for payload in relevant)


@pytest.mark.asyncio
async def test_delivery_idempotent_for_same_job(monkeypatch, tmp_path, caplog):
    storage = await _setup_storage(monkeypatch, tmp_path, tenant="tenant-idem")
    caplog.set_level("INFO", logger="app.observability.structured_logs")

    user_id = 2020
    job_id = "job-idem-2020"
    task_id = "task-idem-2020"
    request_id = "corr-idem-2020"
    url = "https://example.com/result.png"

    await storage.add_generation_job(
        user_id=user_id,
        model_id="demo-model",
        model_name="Demo",
        params={"prompt": "test"},
        price=0.0,
        task_id=task_id,
        status="succeeded",
        job_id=job_id,
        request_id=request_id,
        correlation_id=request_id,
        prompt="test",
        prompt_hash="hash-idem",
        chat_id=user_id,
        message_id=77,
    )
    job = await storage.get_job(job_id)
    assert job is not None

    async def fake_parse_record_info(*_args, **_kwargs):
        return JobResult(
            task_id=task_id,
            state="success",
            media_type="image",
            urls=[url],
            text="done",
            raw={},
        )

    async def fake_validate_result_urls(*_args, **_kwargs):
        return None

    async def fake_resolve(*_args, **_kwargs):
        return "send_document", {"document": "file-id"}

    monkeypatch.setattr(delivery_reconciler, "parse_record_info", fake_parse_record_info)
    monkeypatch.setattr(delivery_reconciler, "_validate_result_urls", fake_validate_result_urls)
    monkeypatch.setattr(delivery_reconciler, "get_model", lambda _model_id: SimpleNamespace(output_media_type="image", model_mode="image", name="Demo"))
    monkeypatch.setattr("app.generations.telegram_sender.resolve_and_prepare_telegram_payload", fake_resolve)

    bot = DummyBot()
    first = await delivery_reconciler.deliver_job_result(
        bot,
        storage,
        job=job,
        status_record={"state": "success", "taskId": task_id},
        notify_user=False,
        source="test_idempotent",
    )
    second = await delivery_reconciler.deliver_job_result(
        bot,
        storage,
        job=job,
        status_record={"state": "success", "taskId": task_id},
        notify_user=False,
        source="test_idempotent",
    )

    assert first is True
    assert second is True
    send_calls = [call for call in bot.calls if call[0] == "send_document"]
    assert len(send_calls) == 1

    delivery_records = await storage.read_json_file("delivery_records.json", default={})
    record = delivery_records.get(f"{user_id}:{task_id}") or {}
    assert record.get("status") == "delivered"

    payloads = _structured_payloads(caplog)
    send_ok_events = [payload for payload in payloads if payload.get("action") == "DELIVERY_SEND_OK"]
    assert len(send_ok_events) == 1
