from types import SimpleNamespace

from telegram import Update
from telegram.ext import CallbackQueryHandler

import bot_kie
from app.helpers.copy import build_step1_prompt_text
from app.pricing.ssot_catalog import get_sku_by_id, resolve_sku_for_params
from bot_kie import button_callback


async def test_step1_prompt_flow_snapshot(harness):
    user_id = 55502
    harness.add_handler(CallbackQueryHandler(button_callback))
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    callback_gen = harness.create_mock_callback_query("gen_type:text-to-image", user_id=user_id)
    update_gen = Update(update_id=201, callback_query=callback_gen)
    harness._attach_bot(update_gen)
    await button_callback(update_gen, context)

    callback_model = harness.create_mock_callback_query("select_model:z-image", user_id=user_id)
    update_model = Update(update_id=202, callback_query=callback_model)
    harness._attach_bot(update_model)
    await button_callback(update_model, context)

    message = harness.outbox.get_last_message()
    assert message is not None

    session = bot_kie.user_sessions[user_id]
    model_id = session.get("model_id")
    params = session.get("params") or {}
    user_lang = bot_kie.get_user_language(user_id)
    mode_index = bot_kie._resolve_mode_index(model_id, params, user_id)
    price_text = bot_kie._build_current_price_line(
        session,
        user_lang=user_lang,
        model_id=model_id,
        mode_index=mode_index,
        gen_type=session.get("gen_type"),
        params=params,
        correlation_id="corr-test",
        update_id=202,
        action_path="test_step1_prompt_flow",
        user_id=user_id,
        chat_id=user_id,
        is_admin=bot_kie.get_is_admin(user_id),
    )

    sku_id = session.get("sku_id")
    sku = get_sku_by_id(sku_id) if sku_id else None
    if not sku:
        sku = resolve_sku_for_params(model_id, params)

    price_quote = session.get("price_quote") or {}
    breakdown = price_quote.get("breakdown", {}) if isinstance(price_quote, dict) else {}
    price_rub = price_quote.get("price_rub") if isinstance(price_quote, dict) else None
    is_free = bool(breakdown.get("free_sku")) or str(price_rub) in {"0", "0.0", "0.00"}
    billing_ctx = {
        "price_text": price_text,
        "price_rub": price_rub,
        "is_free": is_free,
    }

    expected = build_step1_prompt_text(
        model_id,
        sku,
        billing_ctx,
        admin_flag=bot_kie.get_is_admin(user_id),
    )

    assert message["text"] == expected
