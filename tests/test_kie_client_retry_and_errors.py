import random

import pytest

from app.kie.kie_client import KIEClient


def test_backoff_delay_caps_max(monkeypatch):
    client = KIEClient(base_delay=1.0, max_delay=4.0)
    monkeypatch.setattr(random, "uniform", lambda *_args, **_kwargs: 0.0)

    delay = client._backoff_delay(attempt=4, status=500)
    assert delay == 4.0

    delay_429 = client._backoff_delay(attempt=3, status=429)
    assert delay_429 == 4.0


def test_error_mapping_codes():
    client = KIEClient()
    mapping = {
        401: "unauthorized",
        402: "payment_required",
        422: "validation_error",
        429: "rate_limited",
        503: "server_error",
    }
    for status, code in mapping.items():
        error = client._classify_error(status=status, message="msg", correlation_id="abc123")
        assert error.code == code
