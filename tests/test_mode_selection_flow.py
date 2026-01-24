from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram import Update

from app.generations.universal_engine import JobResult
from app.kie_catalog import get_model_map
from app.pricing.price_resolver import PriceQuote
from bot_kie import button_callback, confirm_generation, user_sessions, FREE_TOOL_MODEL_IDS
from tests.ptb_harness import PTBHarness


def _pick_multimode_model():
    for spec in get_model_map().values():
        if len(spec.modes) > 1 and spec.id not in FREE_TOOL_MODEL_IDS:
            return spec
    return None


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


@pytest.mark.asyncio
async def test_mode_selection_price_charge_and_generation(monkeypatch):
    spec = _pick_multimode_model()
    if not spec:
        pytest.skip("No multi-mode paid model found")

    harness = PTBHarness()
    await harness.setup()
    user_id = 9911
    context = SimpleNamespace(bot=harness.application.bot, user_data={})
    captured_mode_index = {}

    async def fake_get_balance(_user_id):
        return 100.0

    async def fake_subtract_balance(_user_id, amount):
        captured_mode_index["charged"] = amount
        return True

    def fake_resolve_price_quote(model_id, mode_index, gen_type, selected_params, settings=None, is_admin=False):
        captured_mode_index["mode_index"] = mode_index
        return PriceQuote(
            price_rub=Decimal("12.00"),
            currency="RUB",
            breakdown={"mode_index": mode_index, "model_id": model_id, "params": dict(selected_params or {})},
            sku_id=f"{model_id}::test",
        )

    async def fake_run_generation(*_args, **_kwargs):
        return JobResult(
            task_id="task-123",
            state="success",
            media_type="image",
            urls=["https://example.com/result.png"],
            text=None,
            raw={"elapsed": 0.1},
        )

    monkeypatch.setattr("bot_kie.get_user_balance_async", fake_get_balance)
    monkeypatch.setattr("bot_kie.subtract_user_balance_async", fake_subtract_balance)
    monkeypatch.setattr("app.pricing.price_resolver.resolve_price_quote", fake_resolve_price_quote)
    monkeypatch.setattr(
        "bot_kie.check_free_generation_available",
        AsyncMock(return_value={"status": "skip"}),
    )
    monkeypatch.setattr(
        "bot_kie.is_free_generation_available",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "bot_kie.get_user_free_generations_remaining",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "bot_kie.get_free_counter_line",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr("bot_kie._kie_readiness_state", lambda: (True, "ok"))
    monkeypatch.setattr("bot_kie.get_is_admin", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        "kie_input_adapter.normalize_for_generation",
        lambda _model_id, params: (params, []),
    )
    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

    callback_select = harness.create_mock_callback_query(f"select_model:{spec.id}", user_id=user_id)
    update_select = Update(update_id=201, callback_query=callback_select)
    harness._attach_bot(update_select)
    await button_callback(update_select, context)
    mode_prompt = harness.outbox.get_last_edited_message()
    assert mode_prompt is not None
    assert "режим" in mode_prompt["text"].lower()

    callback_mode = harness.create_mock_callback_query(f"select_mode:{spec.id}:1", user_id=user_id)
    update_mode = Update(update_id=202, callback_query=callback_mode)
    harness._attach_bot(update_mode)
    await button_callback(update_mode, context)

    session = user_sessions[user_id]
    session["params"] = _build_dummy_params(spec)
    session["waiting_for"] = None
    session["current_param"] = None

    callback_confirm = harness.create_mock_callback_query("confirm_generate", user_id=user_id)
    update_confirm = Update(update_id=203, callback_query=callback_confirm)
    harness._attach_bot(update_confirm)
    await confirm_generation(update_confirm, context)

    assert captured_mode_index.get("mode_index") == 1

    preview_found = any(
        "перед запуском" in (msg.get("text") or "").lower()
        for msg in harness.outbox.edited_messages
    )
    assert preview_found

    user_sessions.pop(user_id, None)
    await harness.teardown()


@pytest.mark.asyncio
async def test_mode_selection_hides_unpriced_modes(monkeypatch):
    spec = _pick_multimode_model()
    if not spec:
        pytest.skip("No multi-mode paid model found")

    harness = PTBHarness()
    await harness.setup()
    user_id = 9922
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    def fake_resolve_price_quote(model_id, mode_index, gen_type, selected_params, settings=None, is_admin=False):
        if mode_index == 1 and not selected_params:
            return None
        return PriceQuote(
            price_rub=Decimal("5.00"),
            currency="RUB",
            breakdown={
                "mode_index": mode_index,
                "model_id": model_id,
                "params": {"resolution": "1K"},
            },
            sku_id=f"{model_id}::resolution=1K",
        )

    monkeypatch.setattr("app.pricing.price_resolver.resolve_price_quote", fake_resolve_price_quote)
    monkeypatch.setattr("bot_kie.get_is_admin", lambda *_args, **_kwargs: False)

    callback_select = harness.create_mock_callback_query(f"select_model:{spec.id}", user_id=user_id)
    update_select = Update(update_id=301, callback_query=callback_select)
    harness._attach_bot(update_select)
    await button_callback(update_select, context)

    mode_prompt = harness.outbox.get_last_edited_message()
    assert mode_prompt is not None
    reply_markup = mode_prompt.get("reply_markup")
    assert reply_markup is not None
    select_mode_callbacks = [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if isinstance(button.callback_data, str) and button.callback_data.startswith("select_mode:")
    ]
    assert f"select_mode:{spec.id}:0" in select_mode_callbacks
    assert f"select_mode:{spec.id}:1" not in select_mode_callbacks

    user_sessions.pop(user_id, None)
    await harness.teardown()
