from decimal import Decimal

from bot_kie import calculate_price_rub, format_rub_amount, _build_price_preview_text


def test_price_shown_equals_price_charged():
    price = calculate_price_rub("z-image", {"prompt": "test", "aspect_ratio": "1:1"})
    assert price is not None
    shown = format_rub_amount(price)
    preview = _build_price_preview_text("ru", price, price + 10)
    assert shown in preview
    shown_value = Decimal(shown.split()[0])
    assert shown_value == Decimal(str(price)).quantize(Decimal("0.01"))
