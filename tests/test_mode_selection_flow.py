from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.generations.universal_engine import JobResult
from app.kie_catalog import get_model_map
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

    def fake_price_for_model_rub(model_id, mode_index, settings, *, is_admin=False):
        captured_mode_index["mode_index"] = mode_index
        return 12

    async def fake_run_generation(*_args, **_kwargs):
        return JobResult(
            task_id="task-123",
            state="success",
            media_type="image",
            urls=["https://example.com/result.png"],
            text=None,
            raw={"elapsed": 0.1},
        )

    monkeypatch.setattr("app.services.user_service.get_user_balance", fake_get_balance)
    monkeypatch.setattr("app.services.user_service.subtract_user_balance", fake_subtract_balance)
    monkeypatch.setattr("app.services.pricing_service.price_for_model_rub", fake_price_for_model_rub)
    monkeypatch.setattr(
        "kie_input_adapter.normalize_for_generation",
        lambda _model_id, params: (params, []),
    )
    monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

    update_select = harness.create_mock_update_callback(f"select_model:{spec.id}", user_id=user_id)
    await button_callback(update_select, context)
    mode_prompt = harness.outbox.get_last_edited_message()
    assert mode_prompt is not None
    assert "режим" in mode_prompt["text"].lower()

    update_mode = harness.create_mock_update_callback(f"select_mode:{spec.id}:1", user_id=user_id)
    await button_callback(update_mode, context)

    session = user_sessions[user_id]
    session["params"] = _build_dummy_params(spec)
    session["waiting_for"] = None
    session["current_param"] = None

    update_confirm = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
    await confirm_generation(update_confirm, context)

    assert captured_mode_index.get("mode_index") == 1
    assert "charged" in captured_mode_index

    preview_found = any(
        "перед запуском" in (msg.get("text") or "").lower()
        for msg in harness.outbox.edited_messages
    )
    assert preview_found

    user_sessions.pop(user_id, None)
    await harness.teardown()
