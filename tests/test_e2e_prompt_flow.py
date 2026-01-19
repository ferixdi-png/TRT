import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot_kie import button_callback, input_parameters, start


@pytest.mark.asyncio
async def test_e2e_text_prompt_flow(harness):
    user_id = 24567
    harness.add_handler(CommandHandler("start", start))
    harness.add_handler(CallbackQueryHandler(button_callback))
    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))

    result = await harness.process_command("/start", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback("gen_type:text-to-image", user_id=user_id)
    assert result["success"]

    result = await harness.process_callback("select_model:z-image", user_id=user_id)
    assert result["success"]

    result = await harness.process_message("A calm lake at sunrise", user_id=user_id)
    assert result["success"]
