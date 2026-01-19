from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.delivery import result_delivery


@pytest.mark.asyncio
async def test_delivery_html_as_photo_does_not_happen(monkeypatch):
    async def fake_download(session, url, **kwargs):
        return result_delivery.DeliveryTarget(
            url=url,
            data=b"<html><body>preview</body></html>",
            content_type="text/html",
            size_bytes=64,
        )

    monkeypatch.setattr(result_delivery, "_download_with_retries", fake_download)

    bot = SimpleNamespace(
        send_photo=AsyncMock(),
        send_document=AsyncMock(),
        send_message=AsyncMock(),
        send_video=AsyncMock(),
        send_audio=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)

    await result_delivery.deliver_generation_result(
        context,
        chat_id=1,
        correlation_id="corr-test",
        model_id="model-x",
        gen_type="text_to_image",
        result_urls=["https://example.com/result"],
        caption_text="done",
    )

    assert bot.send_photo.call_count == 0
    assert bot.send_message.call_count >= 1


@pytest.mark.asyncio
async def test_delivery_content_type_overrides_url_extension(monkeypatch):
    async def fake_download(session, url, **kwargs):
        return result_delivery.DeliveryTarget(
            url=url,
            data=b"<html><body>preview</body></html>",
            content_type="text/html",
            size_bytes=64,
        )

    monkeypatch.setattr(result_delivery, "_download_with_retries", fake_download)

    bot = SimpleNamespace(
        send_photo=AsyncMock(),
        send_document=AsyncMock(),
        send_message=AsyncMock(),
        send_video=AsyncMock(),
        send_audio=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)

    await result_delivery.deliver_generation_result(
        context,
        chat_id=1,
        correlation_id="corr-test",
        model_id="model-x",
        gen_type="text_to_image",
        result_urls=["https://example.com/result.png"],
        caption_text="done",
    )

    assert bot.send_photo.call_count == 0
    assert bot.send_message.call_count >= 1
