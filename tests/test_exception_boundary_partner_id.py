from __future__ import annotations

import pytest

from app.observability.exception_boundary import handle_unknown_callback


class DummyUpdate:
    update_id = 42


class DummyContext:
    def __init__(self) -> None:
        self.user_data = {}


@pytest.mark.asyncio
async def test_unknown_callback_uses_partner_id_fallback(monkeypatch, caplog) -> None:
    monkeypatch.delenv("BOT_INSTANCE_ID", raising=False)
    monkeypatch.setenv("PARTNER_ID", "partner-99")

    await handle_unknown_callback(DummyUpdate(), DummyContext(), callback_data="back_to_menu")

    assert any("partner-99" in record.message for record in caplog.records)
