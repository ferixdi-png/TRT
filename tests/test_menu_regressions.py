import pytest
from telegram.ext import CallbackQueryHandler, CommandHandler

import bot_kie
from bot_kie import UI_CONTEXT_MAIN_MENU, _build_free_tools_keyboard, button_callback, start
from app.kie_catalog.catalog import get_free_tools_model_ids
from app.models.registry import get_models_sync
from app.pricing.ssot_catalog import get_sku_by_id


def _collect_callback_data(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


@pytest.mark.asyncio
async def test_start_returns_menu(harness):
    harness.add_handler(CommandHandler("start", start))
    bot_kie._processed_update_ids.clear()
    user_id = 4242

    result = await harness.process_command("/start", user_id=user_id)

    assert result["success"], f"Command failed: {result.get('error')}"
    assert result["outbox"]["messages"], "Main menu should send a message"
    session = bot_kie.user_sessions.get(user_id)
    assert session is not None
    assert session.get("ui_context") == UI_CONTEXT_MAIN_MENU


@pytest.mark.asyncio
async def test_back_to_menu_context_reset(harness):
    harness.add_handler(CallbackQueryHandler(button_callback))
    user_id = 4343
    session = bot_kie.user_sessions.ensure(user_id)
    session.update(
        {
            "ui_context": bot_kie.UI_CONTEXT_FREE_TOOLS_MENU,
            "waiting_for": "prompt",
            "current_param": "prompt",
            "model_id": "z-image",
        }
    )

    result = await harness.process_callback("back_to_menu", user_id=user_id)

    assert result["success"], f"Callback failed: {result.get('error')}"
    session_after = bot_kie.user_sessions.get(user_id)
    assert session_after is not None
    assert session_after.get("ui_context") == UI_CONTEXT_MAIN_MENU
    assert "waiting_for" not in session_after
    assert "current_param" not in session_after


def test_free_tools_exact_count_9_and_no_duplicates():
    free_ids = get_free_tools_model_ids(log_selection=False)
    models_map = {model["id"]: model for model in get_models_sync()}
    free_skus = [get_sku_by_id(sku_id) for sku_id in free_ids]
    free_skus = [sku for sku in free_skus if sku and sku.model_id in models_map]
    markup, tool_count = _build_free_tools_keyboard(
        free_skus=free_skus,
        models_map=models_map,
        user_lang="ru",
    )
    callbacks = _collect_callback_data(markup)
    assert tool_count == 9
    assert len(callbacks) == len(set(callbacks))
