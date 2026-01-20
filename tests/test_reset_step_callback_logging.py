import logging

import pytest
from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback


@pytest.mark.asyncio
async def test_reset_step_does_not_log_unknown_callback(harness, caplog):
    caplog.set_level(logging.INFO)
    harness.add_handler(CallbackQueryHandler(button_callback))

    await harness.process_callback("reset_step", user_id=12345)

    assert "UI_UNKNOWN_CALLBACK" not in caplog.text
