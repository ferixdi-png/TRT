import os
from pathlib import Path

from telegram.ext import CallbackQueryHandler

from bot_kie import button_callback, user_sessions


async def test_payment_flow_sbp_waiting_for_screenshot(harness, monkeypatch):
    harness.add_handler(CallbackQueryHandler(button_callback))
    async def _fake_balance(_user_id: int) -> float:
        return 0.0
    monkeypatch.setattr("bot_kie.get_user_balance_async", _fake_balance)
    monkeypatch.setattr("bot_kie._should_dedupe_update", lambda *args, **kwargs: False)
    data_dir = Path(os.environ["STORAGE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    balances_path = data_dir / "user_balances.json"
    if not balances_path.exists():
        balances_path.write_text("{}", encoding="utf-8")

    result = await harness.process_callback("topup_balance", user_id=12345)
    assert result["success"], result.get("error")
    result = await harness.process_callback("topup_amount:50", user_id=12345)
    assert result["success"], result.get("error")
    result = await harness.process_callback("pay_sbp:50.0", user_id=12345)
    assert result["success"], result.get("error")

    session = user_sessions[12345]
    assert session.get("waiting_for") == "payment_screenshot"
    assert session.get("payment_method") == "sbp"
    assert session.get("topup_amount") == 50.0
