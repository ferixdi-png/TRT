"""Ensure free models resolve to a zero price quote."""

import bot_kie
from app.pricing.price_ssot import list_free_sku_keys, list_model_skus


def test_free_model_price_is_zero_or_free():
    free_skus = list_free_sku_keys()
    assert free_skus
    sku_id = free_skus[0]
    model_id = sku_id.split("::", 1)[0]
    skus = list_model_skus(model_id)
    sku = next(item for item in skus if item.sku_key == sku_id)

    session = {}
    quote = bot_kie._update_price_quote(
        session,
        model_id=model_id,
        mode_index=0,
        gen_type=None,
        params=sku.params,
        correlation_id="corr-free-quote",
        update_id=1,
        action_path="test_free_quote",
        user_id=1,
        chat_id=1,
        is_admin=False,
    )

    assert quote is not None
    assert float(quote["price_rub"]) == 0.0
    assert session.get("sku_id") == sku_id
