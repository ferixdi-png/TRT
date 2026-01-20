import pytest

import bot_kie
from app.pricing.price_resolver import format_price_rub
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_start_next_parameter_enum_prices(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    user_id = 4242
    try:
        async def fake_free_counter_line(*_args, **_kwargs):
            return ""

        def fake_price_line(*_args, **_kwargs):
            return "price"

        def fake_language(_user_id):
            return "ru"

        def fake_get_param_price_variants(model_id, param_name, current_params):
            return True, {"small": 10.0, "large": 25.5}

        monkeypatch.setattr(bot_kie, "_resolve_free_counter_line", fake_free_counter_line)
        monkeypatch.setattr(bot_kie, "_build_current_price_line", fake_price_line)
        monkeypatch.setattr(bot_kie, "get_user_language", fake_language)
        monkeypatch.setattr(bot_kie, "_get_param_price_variants", fake_get_param_price_variants)

        bot_kie.user_sessions[user_id] = {
            "model_id": "model-x",
            "properties": {
                "size": {
                    "type": "string",
                    "enum": ["small", "medium", "large"],
                    "description": "",
                    "required": True,
                }
            },
            "params": {},
            "required": ["size"],
        }

        update = harness.create_mock_update_command("/start", user_id=user_id)
        context = type("Context", (), {"bot": harness.application.bot})

        await bot_kie.start_next_parameter(update, context, user_id)

        message = harness.outbox.get_last_message()
        assert message is not None
        keyboard = message["reply_markup"].inline_keyboard
        labels = [button.text for row in keyboard for button in row]
        expected_small = f"small — {format_price_rub(10.0)}₽"
        expected_large = f"large — {format_price_rub(25.5)}₽"
        assert expected_small in labels
        assert expected_large in labels
        assert "medium" not in "".join(labels)
        assert expected_small in message["text"]
        assert expected_large in message["text"]
    finally:
        bot_kie.user_sessions.pop(user_id, None)
        await harness.teardown()
