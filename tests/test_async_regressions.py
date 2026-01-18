from types import SimpleNamespace

import asyncio
import pytest

import bot_kie
from app.services.user_service import get_user_balance as get_user_balance_async
from tests.ptb_harness import PTBHarness


@pytest.mark.asyncio
async def test_main_menu_no_asyncio_run_and_missing_storage_defaults(test_env, monkeypatch):
    harness = PTBHarness()
    await harness.setup()
    update = harness.create_mock_update_command("/start", user_id=4242)
    context = SimpleNamespace(bot=harness.application.bot, user_data={})

    def _boom(*args, **kwargs):
        raise AssertionError("asyncio.run should not be called in async menu flow")

    monkeypatch.setattr(asyncio, "run", _boom)

    try:
        await bot_kie.show_main_menu(update, context, source="test_main_menu")
        assert harness.outbox.messages
    finally:
        await harness.teardown()


@pytest.mark.asyncio
async def test_add_payment_async_credits_balance(test_env):
    user_id = 5050
    start_balance = await get_user_balance_async(user_id)
    payment = await bot_kie.add_payment_async(user_id, 12.5, screenshot_file_id="test_file_id")
    end_balance = await get_user_balance_async(user_id)

    assert payment["user_id"] == user_id
    assert end_balance >= start_balance + 12.5
