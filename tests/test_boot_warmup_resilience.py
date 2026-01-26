import asyncio
import re

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


@pytest.mark.asyncio
async def test_boot_warmup_ready_then_cancel_has_no_timeout(monkeypatch, caplog):
    async def slow_models_cache(*args, **kwargs):
        await asyncio.sleep(0.2)

    async def slow_gen_menu_warmup(*args, **kwargs):
        await asyncio.sleep(0.2)

    ready_event = asyncio.Event()

    monkeypatch.setattr(bot_kie, "_webhook_app_ready_event", ready_event)
    monkeypatch.setattr(bot_kie, "_warm_models_cache", slow_models_cache)
    monkeypatch.setattr(bot_kie, "warm_generation_type_menu_cache", slow_gen_menu_warmup)
    monkeypatch.setattr(bot_kie, "BOOT_WARMUP_WATCHDOG_SECONDS", 0.1)

    caplog.set_level("INFO")
    task = bot_kie.start_boot_warmups(correlation_id="TEST_BOOT_READY_CANCEL")
    await asyncio.sleep(0.02)
    ready_event.set()
    await asyncio.sleep(0.02)
    task.cancel()
    await task

    assert not any("BOOT_WARMUP_WATCHDOG_TIMEOUT" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_gen_type_warmup_timeout_elapsed_is_per_attempt(caplog):
    async def slow_warmup():
        await asyncio.sleep(0.2)
        return {}

    caplog.set_level("INFO")
    await bot_kie.warm_generation_type_menu_cache(
        correlation_id="TEST_WARMUP_ELAPSED",
        timeout_s=0.05,
        warmup_fn=slow_warmup,
        retry_attempts=1,
        force=True,
    )

    assert "GEN_TYPE_MENU_WARMUP_TIMEOUT" in caplog.text
    match = re.search(r"GEN_TYPE_MENU_WARMUP_TIMEOUT elapsed_ms=(\d+)", caplog.text)
    assert match, "expected elapsed_ms in timeout log"
    elapsed_ms = int(match.group(1))
    assert elapsed_ms <= 200
