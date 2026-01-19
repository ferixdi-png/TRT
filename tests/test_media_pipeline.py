import asyncio
from unittest.mock import AsyncMock

from telegram import InputFile

from app.generations.media_pipeline import resolve_and_prepare_telegram_payload


class DummyResponse:
    def __init__(self, *, headers=None, body=b"", history=None, content_length=None):
        self.headers = headers or {}
        self._body = body
        self.history = history or []
        self.content_length = content_length

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def __init__(self, head_factory, get_factory):
        self._head_factory = head_factory
        self._get_factory = get_factory
        self.last_head_url = None

    def head(self, url, *args, **kwargs):
        self.last_head_url = url
        return self._head_factory()

    def get(self, url, *args, **kwargs):
        return self._get_factory()


def test_media_html_url_downloads_bytes_and_sends_inputfile():
    head_response = DummyResponse(headers={"Content-Type": "text/html"}, content_length=1024)
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data")
    session = DummySession(lambda: head_response, lambda: get_response)

    tg_method, payload = asyncio.run(
        resolve_and_prepare_telegram_payload(
            {"urls": ["https://example.com/result.html"], "text": None},
            "corr-1",
            "image",
            kie_client=None,
            http_client=session,
        )
    )

    assert tg_method == "send_photo"
    assert isinstance(payload["photo"], InputFile)


def test_media_download_url_conversion_used():
    head_response = DummyResponse(headers={"Content-Type": "image/png"}, content_length=1024)
    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data")
    session = DummySession(lambda: head_response, lambda: get_response)

    kie_client = AsyncMock()
    kie_client.base_url = "https://api.kie.ai"
    kie_client.get_download_url = AsyncMock(
        return_value={"ok": True, "url": "https://cdn.kie.ai/direct.png"}
    )

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
    assert session.last_head_url == "https://cdn.kie.ai/direct.png"


def test_unknown_content_type_goes_to_document():
    head_response = DummyResponse(headers={"Content-Type": "application/octet-stream"}, content_length=1024)
    get_response = DummyResponse(headers={"Content-Type": "application/octet-stream"}, body=b"data")
    session = DummySession(lambda: head_response, lambda: get_response)

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
