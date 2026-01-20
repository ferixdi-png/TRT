"""
Ensure menu/welcome text never exposes internal lock warnings.
"""

import pytest
from telegram.ext import CommandHandler

import bot_kie
from app.utils import singleton_lock as lock_utils


BANNED_SUBSTRINGS = ("file-lock", "резервный")


def _reset_dedupe():
    bot_kie._processed_update_ids.clear()


@pytest.mark.asyncio
async def test_menu_text_excludes_internal_lock_warning(harness, monkeypatch):
    monkeypatch.setattr(bot_kie, "get_is_admin", lambda user_id: True)
    lock_utils._set_lock_state("file", True, reason="file_lock_fallback")

    try:
        harness.add_handler(CommandHandler("start", bot_kie.start))
        _reset_dedupe()

        result = await harness.process_command("/start", user_id=12345)
        assert result["success"], f"Command failed: {result.get('error')}"

        payloads = result["outbox"]["messages"] + result["outbox"]["edited_messages"]
        text = "\n".join(payload["text"] for payload in payloads if payload.get("text"))
        lowered = text.lower()
        assert not any(banned in lowered for banned in BANNED_SUBSTRINGS)
    finally:
        lock_utils._set_lock_state("none", True, reason=None)
