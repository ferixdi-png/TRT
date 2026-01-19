import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram import InputFile
from telegram.error import BadRequest

from app.generations.telegram_sender import deliver_result


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
    def __init__(self, get_factory):
        self._get_factory = get_factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        return self._get_factory()


def _make_session(monkeypatch, get_response):
    def factory(*args, **kwargs):
        return DummySession(lambda: get_response)

    monkeypatch.setattr("aiohttp.ClientSession", factory)


def test_deliver_result_url_ok(monkeypatch):
    bot = MagicMock()
    bot.send_photo = AsyncMock()
    bot.send_media_group = AsyncMock()
    bot.send_document = AsyncMock()

    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data")
    _make_session(monkeypatch, get_response)

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="image",
            urls=["https://example.com/image.png"],
            text=None,
            correlation_id="corr-test",
        )
    )

    bot.send_photo.assert_called_once()
    assert isinstance(bot.send_photo.call_args.kwargs["photo"], InputFile)
    assert bot.send_media_group.call_count == 0
    assert bot.send_document.call_count == 0


def test_send_photo_badrequest_falls_back_to_document(monkeypatch):
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=BadRequest("Wrong type of the web page content"))
    bot.send_document = AsyncMock()

    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data")
    _make_session(monkeypatch, get_response)

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="image",
            urls=["https://example.com/bad.png"],
            text=None,
            correlation_id="corr-test",
        )
    )

    bot.send_photo.assert_called_once()
    bot.send_document.assert_called_once()


def test_deliver_result_multi_urls_group_and_sequential(monkeypatch):
    bot = MagicMock()
    bot.send_media_group = AsyncMock()
    bot.send_audio = AsyncMock()

    get_response = DummyResponse(headers={"Content-Type": "image/png"}, body=b"data")
    _make_session(monkeypatch, get_response)

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="image",
            urls=["https://example.com/1.png", "https://example.com/2.png"],
            text=None,
            correlation_id="corr-test",
        )
    )

    bot.send_media_group.assert_called_once()

    audio_get = DummyResponse(headers={"Content-Type": "audio/mpeg"}, body=b"data")
    _make_session(monkeypatch, audio_get)


def test_deliver_result_html_payload_sends_message(monkeypatch):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()

    get_response = DummyResponse(headers={"Content-Type": "text/html"}, body=b"<html></html>")
    _make_session(monkeypatch, get_response)

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="image",
            urls=["https://example.com/not-media"],
            text=None,
            correlation_id="corr-test",
        )
    )

    bot.send_message.assert_called()

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="audio",
            urls=["https://example.com/1.mp3", "https://example.com/2.mp3"],
            text=None,
            correlation_id="corr-test",
        )
    )

    assert bot.send_audio.call_count == 2


def test_deliver_result_video_uses_send_video(monkeypatch):
    bot = MagicMock()
    bot.send_video = AsyncMock()
    bot.send_document = AsyncMock()

    get_response = DummyResponse(headers={"Content-Type": "video/mp4"}, body=b"data")
    _make_session(monkeypatch, get_response)

    asyncio.run(
        deliver_result(
            bot,
            chat_id=1,
            media_type="video",
            urls=["https://example.com/video.mp4"],
            text=None,
            correlation_id="corr-test",
        )
    )

    bot.send_video.assert_called_once()
    assert isinstance(bot.send_video.call_args.kwargs["video"], InputFile)
