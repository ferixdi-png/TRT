from decimal import Decimal

from app.pricing import price_ssot
from app.pricing.price_ssot import PriceSku, list_variants_with_prices


def test_list_variants_with_prices_filters_by_selected_params(monkeypatch):
    skus = [
        PriceSku(
            model_id="model-a",
            sku_key="model-a::size=small|style=a",
            params={"size": "small", "style": "a"},
            price_rub=Decimal("10"),
            unit="request",
        ),
        PriceSku(
            model_id="model-a",
            sku_key="model-a::size=large|style=a",
            params={"size": "large", "style": "a"},
            price_rub=Decimal("20"),
            unit="request",
        ),
        PriceSku(
            model_id="model-a",
            sku_key="model-a::size=small|style=b",
            params={"size": "small", "style": "b"},
            price_rub=Decimal("30"),
            unit="request",
        ),
    ]

    monkeypatch.setattr(price_ssot, "list_model_skus", lambda _model_id: skus)

    variants = list_variants_with_prices("model-a", "size", {"style": "a"})

    assert variants == [("large", Decimal("20")), ("small", Decimal("10"))]
