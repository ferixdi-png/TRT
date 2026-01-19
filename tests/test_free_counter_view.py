import pytest

import bot_kie


@pytest.mark.asyncio
async def test_free_counter_line_format_ru(monkeypatch):
    async def fake_snapshot(user_id):
        return {
            "remaining": 2,
            "limit_per_hour": 5,
            "used_in_current_window": 3,
            "next_refill_in": 17 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="ru",
        correlation_id="corr-test",
        action_path="menu_test",
    )
    assert "Бесплатных осталось: 2 из 5" in line
    assert "Следующая бесплатная через: 17 мин" in line


@pytest.mark.asyncio
async def test_free_counter_line_format_en(monkeypatch):
    async def fake_snapshot(user_id):
        return {
            "remaining": 0,
            "limit_per_hour": 5,
            "used_in_current_window": 5,
            "next_refill_in": 5 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="en",
        correlation_id="corr-test",
        action_path="model_list_test",
    )
    assert "Free remaining: 0 of 5" in line
    assert "Next free in: 5 min" in line


@pytest.mark.asyncio
async def test_free_quota_text_contains_remaining_and_next_refill(monkeypatch):
    async def fake_snapshot(user_id):
        return {
            "remaining": 3,
            "limit_per_hour": 6,
            "used_in_current_window": 3,
            "next_refill_in": 9 * 60,
        }

    monkeypatch.setattr(bot_kie, "get_free_counter_snapshot", fake_snapshot)
    line = await bot_kie.get_free_counter_line(
        1,
        user_lang="ru",
        correlation_id="corr-test",
        action_path="menu_test",
    )
    assert "Бесплатных осталось: 3 из 6" in line
    assert "Следующая бесплатная через: 9 мин" in line
