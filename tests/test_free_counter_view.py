import pytest

import bot_kie


@pytest.mark.asyncio
async def test_free_counter_line_format_ru(monkeypatch):
    monkeypatch.setattr("app.pricing.free_policy.is_sku_free_daily", lambda _sku_id: True)

    async def fake_snapshot(user_id):
        return {
            "remaining": 2,
            "limit_per_day": 5,
            "used_today": 3,
            "next_refill_in": 17 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="ru",
        correlation_id="corr-test",
        action_path="menu_test",
        sku_id="free-sku",
    )
    assert "🎁 Бесплатных осталось сегодня: 2 из 5" in line


@pytest.mark.asyncio
async def test_free_counter_line_format_en(monkeypatch):
    monkeypatch.setattr("app.pricing.free_policy.is_sku_free_daily", lambda _sku_id: True)

    async def fake_snapshot(user_id):
        return {
            "remaining": 0,
            "limit_per_day": 5,
            "used_today": 5,
            "next_refill_in": 5 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="en",
        correlation_id="corr-test",
        action_path="model_list_test",
        sku_id="free-sku",
    )
    assert "🎁 Free remaining today: 0 of 5" in line


@pytest.mark.asyncio
async def test_free_quota_text_contains_remaining_and_next_refill(monkeypatch):
    monkeypatch.setattr("app.pricing.free_policy.is_sku_free_daily", lambda _sku_id: True)

    async def fake_snapshot(user_id):
        return {
            "remaining": 3,
            "limit_per_day": 6,
            "used_today": 3,
            "next_refill_in": 9 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="ru",
        correlation_id="corr-test",
        action_path="menu_test",
        sku_id="free-sku",
    )
    assert "🎁 Бесплатных осталось сегодня: 3 из 6" in line
