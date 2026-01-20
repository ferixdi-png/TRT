import logging

from telegram.ext import CallbackQueryHandler

from app.kie_catalog import get_model
from bot_kie import (
    UI_CONTEXT_FREE_TOOLS_MENU,
    _derive_model_gen_type,
    button_callback,
    user_sessions,
)


async def test_select_model_auto_switches_stale_gen_type(harness, caplog):
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))
    user_id = 44001
    model_id = "midjourney/api"
    model_spec = get_model(model_id)
    derived_gen_type = _derive_model_gen_type(model_spec)

    user_sessions.set(
        user_id,
        {
            "active_gen_type": "image-to-video",
            "gen_type": "image-to-video",
            "ui_context": "FREE_TOOLS_MENU",
        },
    )

    caplog.set_level(logging.INFO)
    result = await harness.process_callback(f"select_model:{model_id}", user_id=user_id)
    assert result["success"], result.get("error")

    session = user_sessions.get(user_id, {})
    assert session.get("model_id") == model_id
    assert session.get("active_gen_type") == derived_gen_type
    assert session.get("gen_type") == derived_gen_type
    assert session.get("waiting_for") is not None
    assert "GEN_TYPE_AUTO_SWITCH_ON_SELECT" in caplog.text


async def test_free_tools_menu_clears_active_gen_type(harness):
    harness.add_handler(CallbackQueryHandler(button_callback, block=True))
    user_id = 44002
    user_sessions.set(
        user_id,
        {
            "active_gen_type": "text-to-video",
            "gen_type": "text-to-video",
            "ui_context": "MODEL_MENU",
        },
    )

    result = await harness.process_callback("free_tools", user_id=user_id)
    assert result["success"], result.get("error")

    session = user_sessions.get(user_id, {})
    assert session.get("active_gen_type") is None
    assert session.get("gen_type") is None
    assert session.get("ui_context") == UI_CONTEXT_FREE_TOOLS_MENU
