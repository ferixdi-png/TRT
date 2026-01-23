import pytest

from app.services.free_tools_service import get_free_generation_status, get_free_tools_config
from app.services.referral_service import (
    award_referral_bonus,
    encode_referral_param,
    list_referrals_for_referrer,
    parse_referral_param,
)
from app.storage.json_storage import JsonStorage
from translations import t


@pytest.mark.asyncio
async def test_parse_referral_param_roundtrip():
    param = encode_referral_param(12345)
    parsed = parse_referral_param(param)
    assert parsed.valid is True
    assert parsed.referrer_id == 12345

    legacy = parse_referral_param("ref_777")
    assert legacy.valid is True
    assert legacy.referrer_id == 777

    invalid = parse_referral_param("ref_invalid")
    assert invalid.valid is False
    assert invalid.referrer_id is None


@pytest.mark.asyncio
async def test_referral_award_flow(monkeypatch, tmp_path):
    storage = JsonStorage(data_dir=tmp_path, bot_instance_id="test-instance")
    monkeypatch.setattr("app.services.referral_service.get_storage", lambda: storage)
    monkeypatch.setattr("app.services.free_tools_service.get_storage", lambda: storage)

    ref_param = encode_referral_param(101)
    result = await award_referral_bonus(
        referrer_id=101,
        referred_user_id=202,
        ref_param=ref_param,
        correlation_id="corr-test",
        partner_id="test-instance",
        bonus=10,
    )

    assert result["awarded"] is True
    assert await storage.get_referral_free_bank(101) == 10
    assert await storage.get_referral_free_bank(202) == 10

    status = await get_free_generation_status(101)
    assert status["total_remaining"] >= 10

    referred = await list_referrals_for_referrer(101, partner_id="test-instance")
    assert referred == [202]


@pytest.mark.asyncio
async def test_referral_idempotency(monkeypatch, tmp_path):
    storage = JsonStorage(data_dir=tmp_path, bot_instance_id="test-instance")
    monkeypatch.setattr("app.services.referral_service.get_storage", lambda: storage)
    monkeypatch.setattr("app.services.free_tools_service.get_storage", lambda: storage)

    first = await award_referral_bonus(
        referrer_id=111,
        referred_user_id=222,
        ref_param="ref_dup",
        correlation_id="corr-1",
        partner_id="test-instance",
        bonus=10,
    )
    second = await award_referral_bonus(
        referrer_id=111,
        referred_user_id=222,
        ref_param="ref_dup",
        correlation_id="corr-2",
        partner_id="test-instance",
        bonus=10,
    )

    assert first["awarded"] is True
    assert second["awarded"] is False
    assert second["reason"] == "duplicate"
    assert await storage.get_referral_free_bank(111) == 10
    assert await storage.get_referral_free_bank(222) == 10


@pytest.mark.asyncio
async def test_referral_self_ref(monkeypatch, tmp_path):
    storage = JsonStorage(data_dir=tmp_path, bot_instance_id="test-instance")
    monkeypatch.setattr("app.services.referral_service.get_storage", lambda: storage)
    monkeypatch.setattr("app.services.free_tools_service.get_storage", lambda: storage)

    result = await award_referral_bonus(
        referrer_id=333,
        referred_user_id=333,
        ref_param="ref_self",
        correlation_id="corr-self",
        partner_id="test-instance",
        bonus=10,
    )

    assert result["awarded"] is False
    assert result["reason"] == "self_ref"
    assert await storage.get_referral_free_bank(333) == 0


def test_referral_message_contains_bonus():
    bonus = get_free_tools_config().referral_bonus
    text = "\n".join(
        [
            t("msg_referral_title", lang="ru"),
            t("msg_referral_how_it_works", lang="ru", bonus=bonus),
            t("msg_referral_important", lang="ru"),
            t("msg_referral_send", lang="ru", bonus=bonus),
        ]
    )
    assert f"+{bonus}" in text
    assert "+0" not in text
