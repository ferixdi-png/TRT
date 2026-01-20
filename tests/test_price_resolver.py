from decimal import Decimal
from types import SimpleNamespace

from app.pricing.price_resolver import resolve_price_quote


def test_price_resolver_uses_ssot_sku_match():
    settings = SimpleNamespace(usd_to_rub=100.0, price_multiplier=2.0)

    quote = resolve_price_quote(
        model_id="flux-2/flex-text-to-image",
        mode_index=1,
        gen_type="text-to-image",
        selected_params={"resolution": "2K"},
        settings=settings,
        is_admin=False,
    )

    assert quote is not None
    assert quote.price_rub == Decimal("18.86")
    assert quote.breakdown["mode_index"] == 1
    assert quote.breakdown["params"]["resolution"] == "2K"
