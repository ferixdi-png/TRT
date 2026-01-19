import math

from app.services.pricing_service import user_price_rub


def test_price_rounds_up_to_integer_rub():
    price = user_price_rub(0.31132, 77.83, 2.0)
    assert price == math.ceil(0.31132 * 77.83 * 2.0)


def test_price_rounds_up_small_values_to_one():
    price = user_price_rub(0.004, 77.83, 2.0)
    assert price == 1


def test_price_never_zero_for_positive_amount():
    price = user_price_rub(0.00001, 77.83, 2.0)
    assert price == 1


def test_admin_multiplier_is_one():
    admin_price = user_price_rub(1.0, 77.83, 2.0, is_admin=True)
    user_price = user_price_rub(1.0, 77.83, 2.0, is_admin=False)
    assert admin_price == math.ceil(1.0 * 77.83)
    assert user_price == math.ceil(1.0 * 77.83 * 2.0)
