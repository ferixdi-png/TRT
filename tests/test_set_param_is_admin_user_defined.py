from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback, user_sessions
from tests.ptb_harness import PTBHarness


def test_set_param_does_not_raise_nameerror(test_env):
    import asyncio

    harness = PTBHarness()
    asyncio.run(harness.setup())
    harness.add_handler(CallbackQueryHandler(button_callback))

    user_id = 12345
    user_sessions[user_id] = {
        "model_id": "z-image",
        "properties": {"prompt": {"type": "string", "required": True}},
        "required": ["prompt"],
        "params": {},
        "waiting_for": "prompt",
        "current_param": "prompt",
        "model_info": {"name": "Z-Image"},
    }

    result = asyncio.run(harness.process_callback("set_param:prompt:test", user_id=user_id))
    assert result["success"], result
    assert (
        result["outbox"]["messages"]
        or result["outbox"]["edited_messages"]
        or result["outbox"]["callback_answers"]
    )

    asyncio.run(harness.teardown())
