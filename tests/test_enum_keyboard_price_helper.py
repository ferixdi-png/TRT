import pytest

import bot_kie
from app.pricing.price_resolver import format_price_rub


def test_enum_keyboard_filters_and_formats_prices(monkeypatch):
    enum_values = ["small", "medium", "xl"]
    price_map = {"small": 10.0, "xl": 25.5}

    def fake_get_param_price_variants(model_id, param_name, current_params):
        return True, price_map

    monkeypatch.setattr(bot_kie, "_get_param_price_variants", fake_get_param_price_variants)

    keyboard, price_variants_text, display_values = bot_kie.build_enum_keyboard_with_prices(
        param_name="size",
        enum_values=enum_values,
        is_optional=False,
        default_value=None,
        user_lang="ru",
        model_id="model-x",
        current_params={},
    )

    assert display_values == ["small", "xl"]
    expected_small = f"small — {format_price_rub(price_map['small'])}₽"
    expected_xl = f"xl — {format_price_rub(price_map['xl'])}₽"
    labels = [button.text for row in keyboard for button in row]
    assert expected_small in labels
    assert expected_xl in labels
    assert "medium" not in "".join(labels)
    assert expected_small in price_variants_text
    assert expected_xl in price_variants_text
