import pytest
from telegram.ext import MessageHandler, filters

from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_ptb_harness_allows_custom_update_id():
    harness = PTBHarness()
    await harness.setup()

    seen = {}

    async def handler(update, _context):
        seen["update_id"] = update.update_id

    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

    result = await harness.process_message("hi", user_id=111, update_id=42)
    assert result["success"]
    assert seen.get("update_id") == 42

    await harness.teardown()
