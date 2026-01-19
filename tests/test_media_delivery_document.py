import pytest
from unittest.mock import AsyncMock

from app.generations.telegram_sender import deliver_result


aioresponses = pytest.importorskip("aioresponses").aioresponses


@pytest.mark.asyncio
async def test_document_delivery_uses_send_document():
    bot = AsyncMock()
    url = "https://example.com/report.pdf"

    with aioresponses() as mocked:
        mocked.get(
            url,
            body=b"%PDF-1.4\n%mock",
            headers={"Content-Type": "application/pdf"},
        )
        await deliver_result(
            bot,
            chat_id=123,
            media_type="document",
            urls=[url],
            text="Документ готов",
            model_id="doc-model",
            gen_type="document",
            correlation_id="corr-doc",
        )

    bot.send_document.assert_called_once()
