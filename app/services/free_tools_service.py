"""Free tools service for fixed free models and hourly limits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pricing.engine import load_config
from app.kie_catalog.catalog import get_free_tools_model_ids as get_dynamic_free_tools_model_ids
from app.storage import get_storage
from app.observability.structured_logs import log_structured_event
from app.services.user_service import get_is_admin


@dataclass(frozen=True)
class FreeToolsConfig:
    model_ids: List[str]
    base_per_hour: int
    referral_bonus: int


def get_free_tools_config() -> FreeToolsConfig:
    config = load_config()
    free_tools = config.get("free_tools", {}) if isinstance(config, dict) else {}
    model_ids = get_dynamic_free_tools_model_ids(log_selection=False)
    base_per_hour = int(free_tools.get("base_per_hour", 5))
    referral_bonus = int(free_tools.get("referral_bonus", 10))
    return FreeToolsConfig(
        model_ids=list(model_ids),
        base_per_hour=base_per_hour,
        referral_bonus=referral_bonus,
    )


def get_free_tools_model_ids() -> List[str]:
    return get_free_tools_config().model_ids


def _parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        value = datetime.fromisoformat(dt_str)
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_free_generation_status(user_id: int) -> Dict[str, int]:
    storage = get_storage()
    cfg = get_free_tools_config()
    usage = await storage.get_hourly_free_usage(user_id)
    window_start = _parse_iso(usage.get("window_start_iso"))
    used_count = int(usage.get("used_count", 0))
    now = _now()
    if not window_start or now - window_start >= timedelta(hours=1):
        used_count = 0
        window_start = now
    referral_remaining = await storage.get_referral_free_bank(user_id)
    base_remaining = max(0, cfg.base_per_hour - used_count)
    total_remaining = base_remaining + max(0, referral_remaining)
    return {
        "base_remaining": base_remaining,
        "referral_remaining": max(0, referral_remaining),
        "total_remaining": total_remaining,
    }


async def get_free_counter_snapshot(user_id: int, now: Optional[datetime] = None) -> Dict[str, int]:
    cfg = get_free_tools_config()
    storage = get_storage()
    usage = await storage.get_hourly_free_usage(user_id)
    window_start = _parse_iso(usage.get("window_start_iso"))
    used_count = int(usage.get("used_count", 0))
    current_time = now or _now()
    if not window_start or current_time - window_start >= timedelta(hours=1):
        window_start = current_time
        used_count = 0
    limit_per_hour = int(cfg.base_per_hour)
    remaining = max(0, limit_per_hour - used_count)
    next_refill_in = max(0, int((window_start + timedelta(hours=1) - current_time).total_seconds()))
    return {
        "limit_per_hour": limit_per_hour,
        "used_in_current_window": used_count,
        "remaining": remaining,
        "next_refill_in": next_refill_in,
        "window_start_iso": window_start.isoformat(),
    }


def format_free_counter_block(
    remaining: int,
    limit_per_hour: int,
    next_refill_in: int,
    *,
    user_lang: str,
    now: Optional[datetime] = None,
) -> str:
    minutes = max(0, int(next_refill_in / 60))
    local_now = now or datetime.now()
    refill_at = local_now + timedelta(seconds=next_refill_in)
    time_str = refill_at.strftime("%H:%M")
    if user_lang == "en":
        return (
            f"🎁 Free remaining: {remaining} of {limit_per_hour}\n"
            f"⏳ Next free in: {minutes} min (at {time_str} local)"
        )
    return (
        f"🎁 Бесплатных осталось: {remaining} из {limit_per_hour}\n"
        f"⏳ Следующая бесплатная через: {minutes} мин (в {time_str} по локальному времени)"
    )


async def check_and_consume_free_generation(
    user_id: int,
    model_id: str,
    *,
    correlation_id: Optional[str] = None,
) -> Dict[str, object]:
    cfg = get_free_tools_config()
    if model_id not in cfg.model_ids:
        return {"status": "not_free"}
    if get_is_admin(user_id):
        return {"status": "not_free"}

    storage = get_storage()
    usage = await storage.get_hourly_free_usage(user_id)
    window_start = _parse_iso(usage.get("window_start_iso"))
    used_count = int(usage.get("used_count", 0))
    now = _now()

    if not window_start or now - window_start >= timedelta(hours=1):
        window_start = now
        used_count = 0

    base_remaining = cfg.base_per_hour - used_count
    if base_remaining > 0:
        used_count += 1
        await storage.set_hourly_free_usage(
            user_id,
            window_start.isoformat(),
            used_count,
        )
        referral_remaining = await storage.get_referral_free_bank(user_id)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="FREE_QUOTA_UPDATE",
            action_path="free_tools_service.check_and_consume_free_generation",
            stage="FREE_QUOTA",
            outcome="consumed",
            param={
                "model_id": model_id,
                "source": "hourly",
                "base_remaining": max(0, cfg.base_per_hour - used_count),
                "referral_remaining": max(0, referral_remaining),
            },
        )
        return {
            "status": "ok",
            "source": "hourly",
            "base_remaining": max(0, cfg.base_per_hour - used_count),
            "referral_remaining": max(0, referral_remaining),
        }

    referral_remaining = await storage.get_referral_free_bank(user_id)
    if referral_remaining > 0:
        await storage.set_referral_free_bank(user_id, referral_remaining - 1)
        log_structured_event(
            correlation_id=correlation_id,
            user_id=user_id,
            action="FREE_QUOTA_UPDATE",
            action_path="free_tools_service.check_and_consume_free_generation",
            stage="FREE_QUOTA",
            outcome="consumed",
            param={
                "model_id": model_id,
                "source": "referral",
                "base_remaining": 0,
                "referral_remaining": max(0, referral_remaining - 1),
            },
        )
        return {
            "status": "ok",
            "source": "referral",
            "base_remaining": 0,
            "referral_remaining": max(0, referral_remaining - 1),
        }

    reset_in = max(1, int(((window_start + timedelta(hours=1)) - now).total_seconds() / 60))
    return {
        "status": "deny",
        "reset_in_minutes": reset_in,
        "base_remaining": 0,
        "referral_remaining": 0,
    }


async def add_referral_free_bonus(user_id: int, bonus_count: Optional[int] = None) -> int:
    cfg = get_free_tools_config()
    bonus = cfg.referral_bonus if bonus_count is None else int(bonus_count)
    storage = get_storage()
    current = await storage.get_referral_free_bank(user_id)
    new_total = current + bonus
    await storage.set_referral_free_bank(user_id, new_total)
    return new_total
