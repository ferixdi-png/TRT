from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from app.observability.structured_logs import log_structured_event
from app.services.free_tools_service import add_referral_free_bonus, get_free_tools_config
from app.storage import get_storage

REFERRAL_PARAM_PREFIX = "ref_"
REFERRAL_PAYLOAD_PREFIX = "u:"
REFERRAL_EVENTS_FILE = "referral_events.json"


@dataclass(frozen=True)
class ReferralParseResult:
    referrer_id: Optional[int]
    ref_param: Optional[str]
    valid: bool


def _resolve_partner_id() -> str:
    return (os.getenv("PARTNER_ID") or os.getenv("BOT_INSTANCE_ID") or "default").strip() or "default"


def encode_referral_param(user_id: int) -> str:
    payload = f"{REFERRAL_PAYLOAD_PREFIX}{user_id}".encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    return f"{REFERRAL_PARAM_PREFIX}{encoded}"


def _decode_referral_payload(token: str) -> Optional[str]:
    if not token:
        return None
    padding = "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(token + padding)
    except Exception:
        return None
    try:
        return decoded.decode("utf-8")
    except Exception:
        return None


def parse_referral_param(param: Optional[str]) -> ReferralParseResult:
    if not param or not isinstance(param, str):
        return ReferralParseResult(referrer_id=None, ref_param=param, valid=False)
    if not param.startswith(REFERRAL_PARAM_PREFIX):
        return ReferralParseResult(referrer_id=None, ref_param=param, valid=False)
    token = param[len(REFERRAL_PARAM_PREFIX) :]
    if token.isdigit():
        return ReferralParseResult(referrer_id=int(token), ref_param=param, valid=True)
    decoded = _decode_referral_payload(token)
    if not decoded or not decoded.startswith(REFERRAL_PAYLOAD_PREFIX):
        return ReferralParseResult(referrer_id=None, ref_param=param, valid=False)
    value = decoded[len(REFERRAL_PAYLOAD_PREFIX) :]
    if not value.isdigit():
        return ReferralParseResult(referrer_id=None, ref_param=param, valid=False)
    return ReferralParseResult(referrer_id=int(value), ref_param=param, valid=True)


def build_referral_link(user_id: int, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start={encode_referral_param(user_id)}"


def _ensure_events_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"events": {}}
    events = payload.get("events")
    if not isinstance(events, dict):
        payload = dict(payload)
        payload["events"] = {}
    return payload


def _get_event_key(partner_id: str, referred_user_id: int) -> str:
    return f"{partner_id}:{referred_user_id}"


async def list_referrals_for_referrer(
    referrer_id: int,
    *,
    partner_id: Optional[str] = None,
) -> list[int]:
    storage = get_storage()
    partner_id = (partner_id or _resolve_partner_id()).strip() or "default"
    payload = await storage.read_json_file(REFERRAL_EVENTS_FILE, default={})
    payload = _ensure_events_payload(payload)
    events = payload.get("events", {})
    result = []
    for event in events.values():
        if not isinstance(event, dict):
            continue
        if event.get("partner_id") != partner_id:
            continue
        if int(event.get("referrer_id", 0)) != int(referrer_id):
            continue
        if event.get("awarded_at"):
            referred_user = event.get("referred_user_id")
            if isinstance(referred_user, int):
                result.append(referred_user)
            elif isinstance(referred_user, str) and referred_user.isdigit():
                result.append(int(referred_user))
    return result


async def award_referral_bonus(
    *,
    referrer_id: Optional[int],
    referred_user_id: Optional[int],
    ref_param: Optional[str],
    correlation_id: Optional[str],
    partner_id: Optional[str] = None,
    bonus: Optional[int] = None,
) -> Dict[str, Any]:
    partner_id = (partner_id or _resolve_partner_id()).strip() or "default"
    cfg = get_free_tools_config()
    bonus_value = int(bonus if bonus is not None else cfg.referral_bonus)
    awarded = False
    reason = "ok"

    if not referrer_id or not referred_user_id:
        reason = "missing_user"
    elif int(referrer_id) == int(referred_user_id):
        reason = "self_ref"
    else:
        storage = get_storage()
        key = _get_event_key(partner_id, int(referred_user_id))
        created = False
        created_at = datetime.utcnow().isoformat()

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal created
            payload = _ensure_events_payload(data)
            events = payload.get("events", {})
            if key in events:
                payload["events"] = events
                return payload
            events[key] = {
                "partner_id": partner_id,
                "referrer_id": int(referrer_id),
                "referred_user_id": int(referred_user_id),
                "created_at": created_at,
                "awarded_at": created_at,
                "bonus": bonus_value,
            }
            payload["events"] = events
            created = True
            return payload

        await storage.update_json_file(REFERRAL_EVENTS_FILE, updater)

        if not created:
            reason = "duplicate"
        else:
            if hasattr(storage, "set_referrer"):
                await storage.set_referrer(int(referred_user_id), int(referrer_id))
            await add_referral_free_bonus(int(referrer_id), bonus_value)
            awarded = True

    log_structured_event(
        correlation_id=correlation_id,
        user_id=referrer_id,
        action="REFERRAL_AWARDED",
        action_path="referral_service.award_referral_bonus",
        outcome="awarded" if awarded else "skipped",
        param={
            "bonus": bonus_value,
            "awarded": awarded,
            "reason": reason,
            "referrer_id": referrer_id,
            "referred_user_id": referred_user_id,
            "partner_id": partner_id,
            "ref_param": ref_param,
        },
    )
    return {
        "awarded": awarded,
        "reason": reason,
        "bonus": bonus_value,
        "partner_id": partner_id,
    }
