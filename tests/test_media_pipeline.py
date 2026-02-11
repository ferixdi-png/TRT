import asyncio
import os
from unittest.mock import AsyncMock, patch

from telegram import InputFile

from app.generations import media_pipeline
from app.generations.media_pipeline import resolve_and_prepare_telegram_payload

# All tests patch _skip_media_download to False so they exercise download logic
_PATCH_SKIP = patch.object(media_pipeline, '_skip_media_download', return_value=False)


class DummyResponse:
    def __init__(self, *, headers=None, body=b"", history=None, content_length=None, url=None):
        self.headers = headers or {}
        self._body = body
        self.history = history or []
        self.content_length = content_length
        self.url = url  # final resolved URL after redirects
        self.status = 200

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def __init__(self, get_factory):
        self._get_factory = get_factory
        self.last_get_url = None
        self.last_get_kwargs = None

    def get(self, url, *args, **kwargs):
        self.last_get_url = url
        self.last_get_kwargs = kwargs
        return self._get_factory()


def test_media_download_image_uses_inputfile():
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data", url="https://example.com/result.png")
    session = DummySession(lambda: get_response)

    with _PATCH_SKIP:
        tg_method, payload = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://example.com/result.png"], "text": None},
                "corr-1",
                "image",
                kie_client=None,
                http_client=session,
            )
        )

    assert tg_method == "send_photo"
    assert isinstance(payload["photo"], InputFile)


def test_media_download_url_conversion_used():
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data", url="https://cdn.kie.ai/direct.png")
    session = DummySession(lambda: get_response)

    kie_client = AsyncMock()
    kie_client.base_url = "https://api.kie.ai"
    kie_client.get_download_url = AsyncMock(
        return_value={"ok": True, "url": "https://cdn.kie.ai/direct.png"}
    )

    with _PATCH_SKIP:
        tg_method, _ = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://api.kie.ai/original.png"], "text": None},
                "corr-2",
                "image",
                kie_client=kie_client,
                http_client=session,
            )
        )

    assert tg_method == "send_photo"
    assert session.last_get_url == "https://cdn.kie.ai/direct.png"


def test_unknown_content_type_goes_to_document():
    get_response = DummyResponse(headers={"Content-Type": "application/octet-stream"}, body=b"data", url="https://example.com/result.bin")
    session = DummySession(lambda: get_response)

    with _PATCH_SKIP:
        tg_method, payload = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://example.com/result.bin"], "text": None},
                "corr-3",
                "image",
                kie_client=None,
                http_client=session,
            )
        )

    assert tg_method == "send_document"
    assert "document" in payload


def test_html_content_type_returns_message():
    get_response = DummyResponse(headers={"Content-Type": "text/html"}, body=b"<html>ok</html>", url="https://example.com/result.html")
    session = DummySession(lambda: get_response)

    with _PATCH_SKIP:
        tg_method, payload = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://example.com/result.html"], "text": None},
                "corr-4",
                "image",
                kie_client=None,
                http_client=session,
            )
        )

    assert tg_method == "send_message"
    assert "страниц" in payload.get("text", "").lower() or "веб" in payload.get("text", "").lower()


def test_oversized_media_returns_message_without_preview(monkeypatch):
    monkeypatch.setattr(media_pipeline, "TELEGRAM_MAX_BYTES", 1)
    monkeypatch.setattr(media_pipeline, "TELEGRAM_URL_DIRECT", False)
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data", content_length=100, url="https://example.com/big.png")
    session = DummySession(lambda: get_response)

    with _PATCH_SKIP:
        tg_method, payload = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://example.com/big.png"], "text": None},
                "corr-5",
                "image",
                kie_client=None,
                http_client=session,
            )
        )

    assert tg_method == "send_message"
    assert payload.get("disable_web_page_preview") is True


def test_redirect_chain_is_followed():
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data", history=["/redirect"], url="https://example.com/redirect.png")
    session = DummySession(lambda: get_response)

    with _PATCH_SKIP:
        tg_method, _ = asyncio.run(
            resolve_and_prepare_telegram_payload(
                {"urls": ["https://example.com/redirect.png"], "text": None},
                "corr-6",
                "image",
                kie_client=None,
                http_client=session,
            )
        )

    assert tg_method == "send_photo"
