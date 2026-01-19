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


def test_normalize_embedded_http_and_fix_missing_host(monkeypatch):
    monkeypatch.setenv("KIE_API_URL", "https://tempfile.aiquickdraw.com")
    raw = "tempfile.aiquickdraw.comhttps:///f123.png"
    assert normalize_result_url(raw) == "https://tempfile.aiquickdraw.com/f123.png"


def test_normalize_missing_host_without_fallback_raises(monkeypatch):
    monkeypatch.delenv("KIE_API_URL", raising=False)
    with pytest.raises(ResultUrlNormalizationError):
        normalize_result_url("https:///missing-host.png")
