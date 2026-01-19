from pathlib import Path
import re

from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback, user_sessions
from tests.ptb_harness import PTBHarness

BOT_FILE = Path(__file__).parent.parent / "bot_kie.py"


def _extract_callbacks() -> list[str]:
    content = BOT_FILE.read_text(encoding="utf-8", errors="ignore")
    pattern = r"callback_data\s*[=:]\s*[\"']([^\"']+)[\"']"
    callbacks = re.findall(pattern, content)
    return sorted(set(callbacks))


def _normalize_callback(callback: str) -> str:
    if "{" in callback:
        callback = re.sub(r"\{[^}]+\}", "test", callback)
    if callback.endswith(":"):
        return callback + "test"
    if callback.startswith("select_model:"):
        return "select_model:z-image"
    if callback.startswith("model:"):
        return "model:z-image"
    if callback.startswith("modelk:"):
        return "modelk:test"
    if callback.startswith("start:"):
        return "start:z-image"
    if callback.startswith("gen_view:"):
        return "gen_view:1"
    if callback.startswith("gen_repeat:"):
        return "gen_repeat:1"
    if callback.startswith("gen_history:"):
        return "gen_history:1"
    if callback.startswith("payment_screenshot_nav:"):
        return "payment_screenshot_nav:1"
    if callback.startswith("topup_amount:"):
        return "topup_amount:100"
    if callback.startswith("retry_generate:"):
        return "retry_generate:1"
    if callback.startswith("set_param:"):
        return "set_param:prompt:test"
    if callback.startswith("admin_gen_nav:"):
        return "admin_gen_nav:1"
    if callback.startswith("admin_gen_view:"):
        return "admin_gen_view:1"
    if callback.startswith("category:"):
        return "category:Видео"
    if callback.startswith("gen_type:"):
        return "gen_type:text-to-image"
    return callback


def test_no_silence_all_callbacks(monkeypatch, test_env):
    calls = []

    def _collector(level, correlation_id, **fields):
        calls.append({"correlation_id": correlation_id, "fields": fields})

    monkeypatch.setattr("app.observability.trace.trace_event", _collector)
    monkeypatch.setattr("app.observability.no_silence_guard.trace_event", _collector)

    callbacks = [_normalize_callback(cb) for cb in _extract_callbacks()]

    harness = PTBHarness()
    import asyncio
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
    }

    for callback in callbacks:
        before_len = len(calls)
        result = asyncio.run(harness.process_callback(callback, user_id=user_id))
        assert result["success"], f"Callback failed: {callback}"
        assert (
            result["outbox"]["messages"]
            or result["outbox"]["edited_messages"]
            or result["outbox"]["callback_answers"]
        ), f"No user-facing response for {callback}"
        new_calls = calls[before_len:]
        assert any(call["fields"].get("event") == "TRACE_OUT" for call in new_calls), f"No TRACE_OUT for {callback}"

    asyncio.run(harness.teardown())
