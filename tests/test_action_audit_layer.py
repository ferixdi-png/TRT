import json
import logging
from types import SimpleNamespace

import pytest

from app.session_store import get_session_store
from app.observability.structured_logs import log_structured_event
from bot_kie import _register_all_handlers_internal
from tests.ptb_harness import PTBHarness


def _extract_structured_payloads(records):
    payloads = []
    for record in records:
        message = record.message
        if "STRUCTURED_LOG" not in message:
            continue
        _, payload = message.split("STRUCTURED_LOG ", 1)
        payloads.append(json.loads(payload))
    return payloads


@pytest.mark.asyncio
async def test_action_audit_logs_message_and_callback(caplog):
    harness = PTBHarness()
    await harness.setup()
    await _register_all_handlers_internal(harness.application)

    user_id = 4501
    store = get_session_store(application=harness.application)
    store.set(
        user_id,
        {
            "model_id": "seedream/4.5-text-to-image",
            "waiting_for": "prompt",
            "sku_id": "seedream/4.5-text-to-image::aspect_ratio=1:1",
            "price_quote": {"price_rub": "12.34"},
        },
    )

    caplog.set_level(logging.INFO, logger="app.observability.structured_logs")

    await harness.process_message("Hello audit", user_id=user_id)
    await harness.process_callback("show_models", user_id=user_id)

    payloads = _extract_structured_payloads(caplog.records)
    message_payloads = [
        payload for payload in payloads
        if payload.get("action") == "USER_ACTION" and payload.get("update_type") == "message"
    ]
    callback_payloads = [
        payload for payload in payloads
        if payload.get("action") == "USER_ACTION" and payload.get("update_type") == "callback"
    ]

    assert message_payloads, "Expected USER_ACTION log for message"
    assert callback_payloads, "Expected USER_ACTION log for callback"

    message_payload = message_payloads[-1]
    assert message_payload["message_type"] == "text"
    assert message_payload["text_length"] == len("Hello audit")
    assert message_payload["model_id"] == "seedream/4.5-text-to-image"
    assert message_payload["waiting_for"] == "prompt"
    assert message_payload["sku_id"] == "seedream/4.5-text-to-image::aspect_ratio=1:1"
    assert message_payload["price_rub"] == "12.34"

    callback_payload = callback_payloads[-1]
    assert callback_payload["callback_data"] == "show_models"
    assert callback_payload["model_id"] == "seedream/4.5-text-to-image"

    store.clear(user_id)
    await harness.teardown()


def test_structured_logs_include_timestamp_ms(caplog):
    caplog.set_level(logging.INFO, logger="app.observability.structured_logs")

    log_structured_event(action="TEST_EVENT", outcome="ok")

    payloads = _extract_structured_payloads(caplog.records)
    assert payloads, "Expected structured log payloads"
    payload = payloads[-1]
    assert isinstance(payload.get("timestamp_ms"), int)
    assert payload["timestamp_ms"] > 0
