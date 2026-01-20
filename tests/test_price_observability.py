"""Observability tests for price undefined guard blocks."""

import json
import logging
from types import SimpleNamespace

import pytest

import bot_kie
from app.pricing.free_policy import list_free_skus


def _extract_structured_warnings(caplog):
    for record in caplog.records:
        if record.levelno != logging.WARNING:
            continue
        message = record.getMessage()
        if "STRUCTURED_LOG" not in message:
            continue
        _, payload = message.split("STRUCTURED_LOG ", 1)
        yield record, json.loads(payload)


@pytest.mark.asyncio
async def test_price_undefined_emits_warning_log(harness, caplog):
    caplog.set_level(logging.WARNING)
    user_id = 22345
    session = bot_kie.user_sessions.ensure(user_id)
    session["ui_context"] = "GEN_FLOW"
    session["price_quote"] = None

    update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    await bot_kie.respond_price_undefined(
        update,
        context,
        session=session,
        user_lang="ru",
        model_id="test-model",
        gen_type="text",
        sku_id="sku-paid-test",
        price_quote=None,
        free_remaining=0,
        correlation_id="corr-price-test",
        action_path="confirm_generate",
    )

    matches = [
        (record, payload)
        for record, payload in _extract_structured_warnings(caplog)
        if payload.get("action") == "PRICE_UNDEFINED"
    ]
    assert matches
    record, payload = matches[0]
    assert record.levelno == logging.WARNING
    assert payload.get("error_code") == "PAID_NO_QUOTE"


@pytest.mark.asyncio
async def test_free_bypass_bug_is_loud(harness, caplog):
    caplog.set_level(logging.WARNING)
    free_skus = list_free_skus()
    assert free_skus
    sku_id = next(iter(free_skus))

    user_id = 22346
    session = bot_kie.user_sessions.ensure(user_id)
    session["ui_context"] = "GEN_FLOW"
    session["price_quote"] = None

    update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    await bot_kie.respond_price_undefined(
        update,
        context,
        session=session,
        user_lang="ru",
        model_id="test-model",
        gen_type="text",
        sku_id=sku_id,
        price_quote=None,
        free_remaining=1,
        correlation_id="corr-free-test",
        action_path="confirm_generate",
    )

    matches = [
        payload
        for _, payload in _extract_structured_warnings(caplog)
        if payload.get("action") == "PRICE_UNDEFINED"
    ]
    assert matches
    assert any(payload.get("error_code") == "FREE_BYPASS_EXPECTED_BUT_MISSING_QUOTE" for payload in matches)
