import pytest

from app.state import user_state
from price_confirmation import build_confirmation_text


@pytest.mark.asyncio
async def test_build_confirmation_text_async_skips_sync_balance(monkeypatch, caplog):
    def _boom(*args, **kwargs):
        raise AssertionError("sync balance lookup should be skipped in async context")

    monkeypatch.setattr(user_state, "get_user_balance", _boom)
    caplog.set_level("WARNING", logger="price_confirmation")

    text = build_confirmation_text(
        model_id="text-model",
        model_name="Text Model",
        params={"prompt": "hello"},
        price=12.0,
        user_id=101,
        lang="ru",
        is_free=False,
        bonus_available=0.0,
        discount=None,
        correlation_id="corr-async-balance",
    )

    assert "ВАШ БАЛАНС" in text
    assert any(
        "error_code=CONFIRMATION_BALANCE_ASYNC_MISSING" in record.message
        for record in caplog.records
    )
