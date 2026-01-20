"""Free tools service for fixed free models and daily limits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time as time_of_day
from typing import Dict, List, Optional

from pricing.engine import load_config
from app.pricing.free_policy import get_free_daily_limit, is_sku_free_daily, list_free_skus
from app.storage import get_storage
from app.observability.structured_logs import log_structured_event


@dataclass(frozen=True)
class FreeToolsConfig:
    sku_ids: List[str]
    base_per_day: int
    referral_bonus: int


def get_free_tools_config() -> FreeToolsConfig:
    config = load_config()
    free_tools = config.get("free_tools", {}) if isinstance(config, dict) else {}
    sku_ids = list_free_skus()
    _ = free_tools  # config kept for future expansion
    base_per_day = get_free_daily_limit()
    referral_bonus = 0
    return FreeToolsConfig(
        sku_ids=list(sku_ids),
        base_per_day=base_per_day,
        referral_bonus=referral_bonus,
    )


def get_free_tools_model_ids() -> List[str]:
    return get_free_tools_config().sku_ids


def _now() -> datetime:
    return datetime.now()


def _start_of_next_day(current_time: datetime) -> datetime:
    next_day = current_time.date() + timedelta(days=1)
    return datetime.combine(next_day, time_of_day.min)


async def get_free_generation_status(user_id: int) -> Dict[str, int]:
    storage = get_storage()
    cfg = get_free_tools_config()
    used_count = int(await storage.get_user_free_generations_today(user_id))
    base_remaining = max(0, cfg.base_per_day - used_count)
    return {
        "base_remaining": base_remaining,
        "referral_remaining": 0,
        "total_remaining": base_remaining,
    }


async def get_free_counter_snapshot(user_id: int, now: Optional[datetime] = None) -> Dict[str, int]:
    cfg = get_free_tools_config()
    storage = get_storage()
    current_time = now or _now()
    used_count = int(await storage.get_user_free_generations_today(user_id))
    limit_per_day = int(cfg.base_per_day)
    remaining = max(0, limit_per_day - used_count)
    next_refill_at = _start_of_next_day(current_time)
    next_refill_in = max(0, int((next_refill_at - current_time).total_seconds()))
    return {
        "limit_per_day": limit_per_day,
        "used_today": used_count,
        "remaining": remaining,
        "next_refill_in": next_refill_in,
    }


def format_free_counter_block(
    remaining: int,
    limit_per_day: int,
    next_refill_in: int,
    *,
    user_lang: str,
    now: Optional[datetime] = None,
) -> str:
    local_now = now or datetime.now()
    refill_at = local_now + timedelta(seconds=next_refill_in)
    time_str = refill_at.strftime("%H:%M")
    if user_lang == "en":
        if remaining <= 0:
            return (
                f"🎁 Free remaining today: 0 of {limit_per_day}\n"
                f"⏳ Free limit resets tomorrow at {time_str} local.\n"
                "💳 Top up to keep using the tools."
            )
        return (
            f"🎁 Free remaining today: {remaining} of {limit_per_day}\n"
            f"⏳ Free limit resets tomorrow at {time_str} local."
        )
    if remaining <= 0:
        return (
            f"🎁 Бесплатных осталось сегодня: 0 из {limit_per_day}\n"
            f"⏳ Бесплатный лимит обновится завтра в {time_str} по локальному времени.\n"
            "💳 Пополните счет, чтобы продолжить пользоваться инструментами."
        )
    return (
        f"🎁 Бесплатных осталось сегодня: {remaining} из {limit_per_day}\n"
        f"⏳ Бесплатный лимит обновится завтра в {time_str} по локальному времени."
    )


async def check_and_consume_free_generation(
    user_id: int,
    sku_id: str,
    *,
    correlation_id: Optional[str] = None,
) -> Dict[str, object]:
    cfg = get_free_tools_config()
    if not is_sku_free_daily(sku_id):
        return {"status": "not_free_sku"}

    storage = get_storage()
    used_count = int(await storage.get_user_free_generations_today(user_id))
    base_remaining = cfg.base_per_day - used_count
    if base_remaining > 0:
        await storage.increment_free_generations(user_id)
        used_count += 1
        remaining = max(0, cfg.base_per_day - used_count)
        date_key = _now().strftime("%Y-%m-%d")
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="FREE_QUOTA_UPDATE",
            action_path="free_tools_service.check_and_consume_free_generation",
            stage="FREE_QUOTA",
            outcome="consumed",
            param={
                "sku_id": sku_id,
                "used_today": used_count,
                "remaining": remaining,
                "limit_per_day": cfg.base_per_day,
                "date_key": date_key,
            },
        )
        return {
            "status": "ok",
            "used_today": used_count,
            "remaining": remaining,
            "limit_per_day": cfg.base_per_day,
        }

    now = _now()
    reset_in = max(1, int((_start_of_next_day(now) - now).total_seconds() / 60))
    return {
        "status": "deny",
        "reset_in_minutes": reset_in,
        "remaining": 0,
        "limit_per_day": cfg.base_per_day,
    }


async def check_free_generation_available(
    user_id: int,
    sku_id: str,
    *,
    correlation_id: Optional[str] = None,
) -> Dict[str, object]:
    cfg = get_free_tools_config()
    if not is_sku_free_daily(sku_id):
        return {"status": "not_free_sku"}

    storage = get_storage()
    used_count = int(await storage.get_user_free_generations_today(user_id))
    base_remaining = cfg.base_per_day - used_count
    if base_remaining > 0:
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="FREE_QUOTA_CHECK",
            action_path="free_tools_service.check_free_generation_available",
            stage="FREE_QUOTA",
            outcome="available",
            param={
                "sku_id": sku_id,
                "base_remaining": max(0, base_remaining),
            },
        )
        return {
            "status": "ok",
            "base_remaining": max(0, base_remaining),
        }

    now = _now()
    reset_in = max(1, int((_start_of_next_day(now) - now).total_seconds() / 60))
    return {
        "status": "deny",
        "reset_in_minutes": reset_in,
        "base_remaining": 0,
        "referral_remaining": 0,
    }


async def consume_free_generation(
    user_id: int,
    sku_id: str,
    *,
    correlation_id: Optional[str] = None,
    source: str = "delivery",
) -> Dict[str, object]:
    cfg = get_free_tools_config()
    if not is_sku_free_daily(sku_id):
        return {"status": "not_free_sku"}

    storage = get_storage()
    used_count = int(await storage.get_user_free_generations_today(user_id))
    base_remaining = cfg.base_per_day - used_count
    if base_remaining > 0:
        await storage.increment_free_generations(user_id)
        used_count += 1
        remaining = max(0, cfg.base_per_day - used_count)
        date_key = _now().strftime("%Y-%m-%d")
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="FREE_QUOTA_UPDATE",
            action_path="free_tools_service.consume_free_generation",
            stage="FREE_QUOTA",
            outcome="consumed",
            param={
                "sku_id": sku_id,
                "source": source,
                "used_today": used_count,
                "remaining": remaining,
                "limit_per_day": cfg.base_per_day,
                "date_key": date_key,
            },
        )
        return {
            "status": "ok",
            "used_today": used_count,
            "remaining": remaining,
            "limit_per_day": cfg.base_per_day,
        }

    now = _now()
    reset_in = max(1, int((_start_of_next_day(now) - now).total_seconds() / 60))
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="FREE_QUOTA_UPDATE",
        action_path="free_tools_service.consume_free_generation",
        stage="FREE_QUOTA",
        outcome="deny",
        error_code="FREE_QUOTA_EMPTY",
        fix_hint="Пользователь исчерпал бесплатные генерации.",
        param={"sku_id": sku_id, "reset_in_minutes": reset_in},
    )
    return {
        "status": "deny",
        "reset_in_minutes": reset_in,
        "remaining": 0,
        "limit_per_day": cfg.base_per_day,
    }


async def add_referral_free_bonus(user_id: int, bonus_count: Optional[int] = None) -> int:
    cfg = get_free_tools_config()
    bonus = cfg.referral_bonus if bonus_count is None else int(bonus_count)
    storage = get_storage()
    current = await storage.get_referral_free_bank(user_id)
    new_total = current + bonus
    await storage.set_referral_free_bank(user_id, new_total)
    return new_total
