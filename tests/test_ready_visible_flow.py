from types import SimpleNamespace

import pytest

import bot_kie
from app.kie_contract.schema_loader import get_model_schema
from app.models.registry import get_models_sync
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


@pytest.mark.asyncio
async def test_ready_visible_prompt_flow_advances_waiting_for():
    harness = PTBHarness()
    await harness.setup()

    user_id = 5201
    model_id = _pick_ready_visible_model("text_to_image")
    schema = get_model_schema(model_id)
    required = [name for name, spec in schema.items() if isinstance(spec, dict) and spec.get("required")]
    assert required, "Expected required params for READY_VISIBLE model"

    bot_kie.user_sessions[user_id] = {
        "model_id": model_id,
        "model_info": {"name": model_id, "model_type": "text_to_image"},
        "properties": schema,
        "required": required,
        "params": {},
        "waiting_for": required[0],
    }

    update = harness.create_mock_update_message("Test prompt", user_id=user_id)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    await bot_kie.input_parameters(update, context)

    assert bot_kie.user_sessions[user_id].get("waiting_for") != required[0]

    bot_kie.user_sessions.pop(user_id, None)
    await harness.teardown()
