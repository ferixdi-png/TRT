import logging

import pytest
from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback


@pytest.mark.asyncio
async def test_check_balance_button_no_sync_wrapper(harness, caplog):
    caplog.set_level(logging.ERROR)
    harness.add_handler(CallbackQueryHandler(button_callback))

    result = await harness.process_callback("check_balance", user_id=12345)
    assert result["success"], result.get("error")

    payloads = result["outbox"]["edited_messages"] + result["outbox"]["messages"]
    assert payloads
    assert not any(
        "SYNC_WRAPPER_CALLED_IN_ASYNC" in record.message for record in caplog.records
    )
