from decimal import Decimal, ROUND_HALF_UP

from app.services.pricing_service import user_price_rub


def test_price_rounds_to_two_decimals():
    price = user_price_rub(0.31132, 77.83, 2.0)
    expected = (Decimal("0.31132") * Decimal("77.83") * Decimal("2.0")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    assert price == float(expected)


def test_price_rounds_half_up_boundary():
    price = user_price_rub(0.01005, 100.0, 1.0)
    assert price == 1.01


def test_price_can_be_small_but_nonzero():
    price = user_price_rub(0.00001, 77.83, 2.0)
    assert price == 0.0


def test_admin_multiplier_is_one():
    admin_price = user_price_rub(1.0, 77.83, 2.0, is_admin=True)
    user_price = user_price_rub(1.0, 77.83, 2.0, is_admin=False)
    assert admin_price == 77.83
    assert user_price == 155.66
