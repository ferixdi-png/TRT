import re
from types import SimpleNamespace

from telegram import Update
from telegram.ext import CallbackQueryHandler, MessageHandler, filters

from bot_kie import button_callback, input_parameters


async def test_price_shown_on_prompt_flow(harness):
    user_id = 55501
    harness.add_handler(CallbackQueryHandler(button_callback))
    harness.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, input_parameters))
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    callback_gen = harness.create_mock_callback_query("gen_type:text-to-image", user_id=user_id)
    update_gen = Update(update_id=101, callback_query=callback_gen)
    harness._attach_bot(update_gen)
    await button_callback(update_gen, context)

    callback_model = harness.create_mock_callback_query("select_model:z-image", user_id=user_id)
    update_model = Update(update_id=102, callback_query=callback_model)
    harness._attach_bot(update_model)
    await button_callback(update_model, context)

    texts = [m["text"] for m in harness.outbox.messages + harness.outbox.edited_messages]
    assert any("📝 Шаг 1/3: Введите prompt:" in text for text in texts)
    assert any(
        re.search(r"Цена по прайсу: \\d+\\.\\d{2} ₽", text) or "🎁 Бесплатно" in text
        for text in texts
    )

    message = harness.create_mock_message("A calm lake at sunrise", user_id=user_id)
    update_message = Update(update_id=103, message=message)
    harness._attach_bot(update_message)
    await input_parameters(update_message, context)

    texts = [m["text"] for m in harness.outbox.messages + harness.outbox.edited_messages]
    assert any("📝 Шаг 1/3: Введите prompt:" in text for text in texts)
    assert any(
        re.search(r"Цена по прайсу: \\d+\\.\\d{2} ₽", text) or "🎁 Бесплатно" in text
        for text in texts
    )
