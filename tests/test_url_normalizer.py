import pytest

from app.utils.url_normalizer import normalize_result_url, ResultUrlNormalizationError


def test_normalize_http_passthrough():
    url = "https://example.com/result.png"
    assert normalize_result_url(url) == url


def test_normalize_protocol_relative():
    url = "//cdn.example.com/file.mp4"
    assert normalize_result_url(url) == "https://cdn.example.com/file.mp4"


def test_normalize_relative_with_base():
    url = "/assets/file.png"
    assert normalize_result_url(url, base_url="https://cdn.example.com") == "https://cdn.example.com/assets/file.png"


def test_normalize_relative_without_base_raises():
    with pytest.raises(ResultUrlNormalizationError):
        normalize_result_url("/assets/file.png", base_url="")
