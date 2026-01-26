import asyncio

import pytest

import bot_kie


@pytest.mark.asyncio
async def test_webhook_boot_warmup_no_timeout_warnings(monkeypatch, caplog):
    async def slow_models_cache(*args, **kwargs):
        await asyncio.sleep(0.05)

    async def slow_gen_menu_warmup(*args, **kwargs):
        await asyncio.sleep(0.05)

    monkeypatch.setenv("BOT_MODE", "webhook")
    monkeypatch.setattr(bot_kie, "_warm_models_cache", slow_models_cache)
    monkeypatch.setattr(bot_kie, "warm_generation_type_menu_cache", slow_gen_menu_warmup)
    monkeypatch.setattr(bot_kie, "BOOT_WARMUP_WATCHDOG_SECONDS", 0.01)

    caplog.set_level("WARNING")
    task = bot_kie.start_boot_warmups(correlation_id="TEST_BOOT")
    await task

    timeout_warnings = [
        record
        for record in caplog.records
        if "GEN_TYPE_MENU_WARMUP_TIMEOUT" in record.message
        or "MODELS_CACHE_WARMUP_TIMEOUT" in record.message
    ]
    assert not timeout_warnings


@pytest.mark.asyncio
async def test_boot_warmup_cancel_stops_watchdog(monkeypatch, caplog):
    async def slow_models_cache(*args, **kwargs):
        await asyncio.sleep(0.2)

    async def slow_gen_menu_warmup(*args, **kwargs):
        await asyncio.sleep(0.2)

    monkeypatch.setattr(bot_kie, "_warm_models_cache", slow_models_cache)
    monkeypatch.setattr(bot_kie, "warm_generation_type_menu_cache", slow_gen_menu_warmup)
    monkeypatch.setattr(bot_kie, "BOOT_WARMUP_WATCHDOG_SECONDS", 0.5)

    caplog.set_level("INFO")
    task = bot_kie.start_boot_warmups(correlation_id="TEST_BOOT_CANCEL")
    await asyncio.sleep(0.05)
    task.cancel()
    await task

    assert not any("BOOT_WARMUP_WATCHDOG_TIMEOUT" in record.message for record in caplog.records)
