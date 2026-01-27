import asyncio

import pytest

import bot_kie


@pytest.mark.asyncio
async def test_webhook_process_timeout_logs_deterministic(webhook_harness, monkeypatch, caplog):
    async def slow_process_update(_update):
        await asyncio.sleep(0.05)

    monkeypatch.setenv("WEBHOOK_PROCESS_IN_BACKGROUND", "1")
    monkeypatch.setenv("WEBHOOK_PROCESS_TIMEOUT_SECONDS", "0.01")
    webhook_harness.application.bot_data["process_update_override"] = slow_process_update

    caplog.set_level("INFO")
    response = await webhook_harness.send_message(user_id=19101, text="/start", update_id=19101)

    assert response.status == 200
    await asyncio.sleep(0.05)

    assert any("WEBHOOK_PROCESS_TIMEOUT" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_telegram_request_timeout_logs_error_repr(monkeypatch, caplog):
    async def slow_request():
        await asyncio.sleep(0.2)
        return True

    caplog.set_level("WARNING")
    monkeypatch.setenv("WEBHOOK_PROCESS_TIMEOUT_SECONDS", "1.0")

    result = await bot_kie._run_telegram_request(
        "unit_test",
        correlation_id="corr-test",
        timeout_s=0.01,
        retry_attempts=1,
        retry_backoff_s=0.01,
        request_fn=slow_request,
    )

    assert result == (None, True)  # (result, timeout_seen)
    timeout_logs = [record.message for record in caplog.records if "TELEGRAM_REQUEST_TIMEOUT" in record.message]
    assert timeout_logs
    assert "error_repr=" in timeout_logs[0]
