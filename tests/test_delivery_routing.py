import pytest

from app.generations import telegram_sender


class DummyBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id=None, **kwargs):
        self.calls.append(("send_message", chat_id, kwargs))

    async def send_photo(self, chat_id=None, **kwargs):
        self.calls.append(("send_photo", chat_id, kwargs))


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_delivery_routing_text(monkeypatch):
    bot = DummyBot()

    async def fake_resolve(*_args, **_kwargs):
        raise AssertionError("resolve_and_prepare_telegram_payload should not be called for text")

    monkeypatch.setattr(telegram_sender, "resolve_and_prepare_telegram_payload", fake_resolve)

    await telegram_sender.deliver_result(
        bot,
        chat_id=1,
        media_type="text",
        urls=[],
        text="hello",
        correlation_id="corr-test",
    )
    assert bot.calls and bot.calls[0][0] == "send_message"


@pytest.mark.asyncio
async def test_delivery_routing_image(monkeypatch):
    bot = DummyBot()

    async def fake_resolve(*_args, **_kwargs):
        return "send_photo", {"photo": "file"}

    monkeypatch.setattr(telegram_sender, "resolve_and_prepare_telegram_payload", fake_resolve)
    monkeypatch.setattr(telegram_sender.aiohttp, "ClientSession", lambda: DummySession())

    await telegram_sender.deliver_result(
        bot,
        chat_id=1,
        media_type="image",
        urls=["https://example.com/file.png"],
        text=None,
        correlation_id="corr-test",
    )
    assert bot.calls and bot.calls[0][0] == "send_photo"
