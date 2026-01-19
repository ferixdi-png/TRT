import pytest

from app.services.pricing_service import user_price_rub


def test_price_rounds_up_to_two_decimals():
    price = user_price_rub(0.31132, 77.83, 2.0)
    assert price == pytest.approx(48.47)


def test_price_rounds_up_small_values():
    price = user_price_rub(0.004, 77.83, 2.0)
    assert price == pytest.approx(0.63)


def test_price_never_zero_for_positive_amount():
    price = user_price_rub(0.00001, 77.83, 2.0)
    assert price == pytest.approx(0.01)
