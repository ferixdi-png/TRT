from types import SimpleNamespace

import pytest

import bot_kie
from app.kie_contract.schema_loader import get_model_schema
from app.models.registry import get_models_sync
from app.pricing.price_resolver import format_price_rub
from app.ux.model_visibility import evaluate_model_visibility, STATUS_READY_VISIBLE
from tests.ptb_harness import PTBHarness


def _pick_ready_visible_model(model_type: str) -> str:
    for model in get_models_sync():
        if model.get("model_type") != model_type:
            continue
        model_id = model.get("id")
        if evaluate_model_visibility(model_id).status == STATUS_READY_VISIBLE:
            return model_id
    raise AssertionError(f"No READY_VISIBLE model found for {model_type}")


def _pick_priced_param(model_id: str, schema: dict) -> tuple[str, dict]:
    for name, spec in schema.items():
        if not isinstance(spec, dict):
            continue
        enum_values = bot_kie._normalize_enum_values(spec)
        if spec.get("type") != "boolean" and not enum_values:
            continue
        has_price, price_map = bot_kie._get_param_price_variants(model_id, name, {})
        if has_price and price_map:
            return name, price_map
    raise AssertionError(f"No priced enum/boolean param found for {model_id}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_type",
    ["text_to_image", "image_edit", "text_to_video"],
)
async def test_parameter_buttons_include_prices(model_type):
    harness = PTBHarness()
    await harness.setup()

    user_id = abs(hash(model_type)) % 10000 + 6000
    model_id = _pick_ready_visible_model(model_type)
    schema = get_model_schema(model_id)
    param_name, price_map = _pick_priced_param(model_id, schema)
    sample_value, sample_price = next(iter(price_map.items()))

    bot_kie.user_sessions[user_id] = {
        "model_id": model_id,
        "model_info": {"name": model_id, "model_type": model_type},
        "properties": schema,
        "required": [name for name, spec in schema.items() if isinstance(spec, dict) and spec.get("required")],
        "params": {},
    }

    update = harness.create_mock_update_command("/start", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    await bot_kie.prompt_for_specific_param(update, context, user_id, param_name, source="test")

    message = harness.outbox.get_last_message()
    assert message is not None
    keyboard = message["reply_markup"].inline_keyboard
    buttons = [button.text for row in keyboard for button in row]
    expected_price = format_price_rub(sample_price)
    assert any(expected_price in text for text in buttons), (
        f"Expected price {expected_price} to appear in buttons for {model_id}:{param_name}"
    )

    bot_kie.user_sessions.pop(user_id, None)
    await harness.teardown()
