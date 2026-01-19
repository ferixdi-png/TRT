import pytest
import aiohttp

from app.generations import media_pipeline


@pytest.mark.asyncio
async def test_delivery_contract_filename_and_method(monkeypatch):
    async def fake_download(session, url, retries=2):
        return b"\x89PNG\r\n\x1a\n", "image/png", 8

    monkeypatch.setattr(media_pipeline, "_download_with_retries", fake_download)

    async with aiohttp.ClientSession() as session:
        method, payload = await media_pipeline.resolve_and_prepare_telegram_payload(
            {"urls": ["https://example.com/download"]},
            "corr-test",
            "image",
            None,
            session,
        )

    assert method == "send_photo"
    input_file = payload["photo"]
    assert input_file.filename.endswith(".png")
