from telegram.ext import CallbackQueryHandler, MessageHandler, filters

from bot_kie import button_callback, input_parameters, user_sessions
from tests.ptb_harness import PTBHarness


def _trace_collector():
    calls = []

    def _collector(level, correlation_id, **fields):
        calls.append({
            "level": level,
            "correlation_id": correlation_id,
            "fields": fields,
        })

    return calls, _collector


async def test_trace_smoke_callbacks_and_input(monkeypatch, test_env):
    calls, collector = _trace_collector()
    monkeypatch.setattr("app.observability.trace.trace_event", collector)
    monkeypatch.setattr("app.observability.no_silence_guard.trace_event", collector)
    monkeypatch.setattr("bot_kie.trace_event", collector)

    harness = PTBHarness()
    await harness.setup()
    harness.add_handler(CallbackQueryHandler(button_callback))
    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))

    user_id = 12345
    user_sessions[user_id] = {
        "model_id": "z-image",
        "properties": {"prompt": {"type": "string", "required": True}},
        "required": ["prompt"],
        "params": {},
        "waiting_for": "prompt",
        "current_param": "prompt",
    }

    await harness.process_callback("back_to_menu", user_id=user_id)

    update = harness.create_mock_update_command("hello", user_id=user_id)
    harness._attach_bot(update)
    await harness.application.process_update(update)

    await harness.teardown()

    assert any(call["fields"].get("event") == "TRACE_IN" for call in calls)
    assert any(call["fields"].get("event") == "TRACE_OUT" for call in calls)
    assert any(call["fields"].get("stage") == "UI_ROUTER" for call in calls)
    assert any(call["fields"].get("stage") in {"TG_DELIVER", "SESSION_LOAD"} for call in calls)
    assert all(call["correlation_id"].startswith("corr-") for call in calls if call["correlation_id"])
