"""
UX tests for anchored main menu.
"""

from types import SimpleNamespace

import pytest
from telegram.ext import CallbackQueryHandler

import bot_kie
from bot_kie import UI_CONTEXT_MAIN_MENU, button_callback

MAIN_MENU_BUTTONS = [
    "🆓 БЕСПЛАТНЫЕ МОДЕЛИ",
    "📝➡️🖼️ Из текста в фото",
    "🖼️➡️🖼️ Из фото в фото",
    "📝➡️🎬 Из текста в видео",
    "🖼️➡️🎬 Из фото в видео",
    "💳 Баланс",
    "🤝 Партнерка",
]


def _reset_dedupe() -> None:
    bot_kie._processed_update_ids.clear()


def _flatten_keyboard(reply_markup):
    return [button.text for row in reply_markup.inline_keyboard for button in row]


@pytest.mark.asyncio
async def test_cancel_returns_to_main_menu(harness):
    user_id = 12345
    session = bot_kie.user_sessions.ensure(user_id)
    session["waiting_for"] = "prompt"
    session["current_param"] = "prompt"
    session["ui_context"] = "GEN_FLOW"

    harness.add_handler(CallbackQueryHandler(button_callback))
    _reset_dedupe()

    result = await harness.process_callback("cancel", user_id=user_id)

    assert result["success"]
    payloads = result["outbox"]["messages"] + result["outbox"]["edited_messages"]
    assert payloads
    payload_with_menu = next(payload for payload in reversed(payloads) if payload.get("reply_markup"))
    assert _flatten_keyboard(payload_with_menu["reply_markup"]) == MAIN_MENU_BUTTONS
    session_after = bot_kie.user_sessions.get(user_id, {})
    assert session_after.get("ui_context") == UI_CONTEXT_MAIN_MENU


@pytest.mark.asyncio
async def test_error_path_returns_to_main_menu(harness):
    user_id = 12346
    session = bot_kie.user_sessions.ensure(user_id)
    session["waiting_for"] = "prompt"
    session["current_param"] = "prompt"
    session["ui_context"] = "GEN_FLOW"

    update = harness.create_mock_update_callback("confirm_generate", user_id=user_id)
    harness._attach_bot(update)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    await bot_kie.respond_price_undefined(
        update,
        context,
        session=session,
        user_lang="ru",
        model_id="test-model",
        gen_type="text",
        sku_id="sku-test",
        price_quote=None,
        free_remaining=0,
        correlation_id="corr-test",
        action_path="confirm_generate",
    )

    payloads = harness.outbox.messages + harness.outbox.edited_messages
    assert payloads
    payload_with_menu = next(payload for payload in reversed(payloads) if payload.get("reply_markup"))
    assert _flatten_keyboard(payload_with_menu["reply_markup"]) == MAIN_MENU_BUTTONS
    session_after = bot_kie.user_sessions.get(user_id, {})
    assert session_after.get("ui_context") == UI_CONTEXT_MAIN_MENU


@pytest.mark.asyncio
async def test_unknown_callback_returns_to_main_menu(harness):
    harness.add_handler(CallbackQueryHandler(button_callback))
    _reset_dedupe()

    result = await harness.process_callback("unknown_callback:123", user_id=12347)

    assert result["success"]
    payloads = result["outbox"]["messages"] + result["outbox"]["edited_messages"]
    assert payloads
    payload_with_menu = next(payload for payload in reversed(payloads) if payload.get("reply_markup"))
    assert _flatten_keyboard(payload_with_menu["reply_markup"]) == MAIN_MENU_BUTTONS
    session_after = bot_kie.user_sessions.get(12347, {})
    assert session_after.get("ui_context") == UI_CONTEXT_MAIN_MENU
