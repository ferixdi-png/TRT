from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.generations.universal_engine import KIEJobFailed
from bot_kie import ADMIN_ID, confirm_generation, user_sessions
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_kie_fail_state_user_message_and_retry_button(monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    try:
        object.__setattr__(harness.application.bot, "send_photo", AsyncMock())
        object.__setattr__(harness.application.bot, "send_video", AsyncMock())
        object.__setattr__(harness.application.bot, "send_audio", AsyncMock())
        object.__setattr__(harness.application.bot, "send_voice", AsyncMock())
        object.__setattr__(harness.application.bot, "send_document", AsyncMock())
        object.__setattr__(harness.application.bot, "send_media_group", AsyncMock())

        monkeypatch.setattr(
            "kie_input_adapter.normalize_for_generation",
            lambda _model_id, params: (params, []),
        )

        async def fake_run_generation(*_args, **_kwargs):
            raise KIEJobFailed(
                "failed",
                fail_code="KIE_FAIL_STATE",
                fail_msg="oops",
                correlation_id="corr-123",
                record_info={"resultUrls": ["https://example.com/file.png?token=secret"]},
            )

        monkeypatch.setattr("app.generations.universal_engine.run_generation", fake_run_generation)

        user_id = ADMIN_ID
        context = SimpleNamespace(bot=harness.application.bot, user_data={})
        user_sessions[user_id] = {
            "model_id": "z-image",
            "model_info": {"name": "Z Image"},
            "params": {"prompt": "test"},
            "properties": {"prompt": {"type": "string", "required": True}},
            "required": ["prompt"],
            "waiting_for": None,
            "current_param": None,
        }

        update_confirm = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
        await confirm_generation(update_confirm, context)

        last_message = harness.outbox.get_last_edited_message()
        assert last_message is not None
        assert "Генерация не завершилась (KIE)" in last_message["text"]
        markup = last_message["reply_markup"]
        buttons = markup.inline_keyboard if markup else []
        assert any("retry_generate:" in button.callback_data for row in buttons for button in row)
    finally:
        user_sessions.pop(ADMIN_ID, None)
        await harness.teardown()
