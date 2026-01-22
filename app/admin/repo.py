from __future__ import annotations
import csv
import io
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

# Reuse existing data access helpers from bot_kie
from bot_kie import (
    load_json_file,
    USER_REGISTRY_FILE,
    PAYMENTS_FILE,
    GENERATIONS_HISTORY_FILE,
    get_all_users,
    get_all_payments,
)


def _parse_ts(value: Any) -> int:
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # Try ISO8601
            try:
                return int(datetime.fromisoformat(value).timestamp())
            except Exception:
                return int(float(value))
        return 0
    except Exception:
        return 0


def users_summary(page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    data = load_json_file(USER_REGISTRY_FILE, {})
    all_users = get_all_users()
    total = len(all_users)

    # Derive recent users from updated_at where possible
    now = int(time.time())
    day_ago = now - 24 * 3600
    week_ago = now - 7 * 24 * 3600

    new_24h = 0
    new_7d = 0
    enriched: List[Dict[str, Any]] = []

    for uid in all_users:
        rec = data.get(str(uid), {})
        updated_ts = _parse_ts(rec.get("updated_at"))
        if updated_ts >= day_ago:
            new_24h += 1
        if updated_ts >= week_ago:
            new_7d += 1
        enriched.append({
            "user_id": uid,
            "username": rec.get("username"),
            "first_name": rec.get("first_name"),
            "last_name": rec.get("last_name"),
            "updated_at": rec.get("updated_at")
        })

    # Pagination
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    page_items = enriched[start:end]

    return {
        "total": total,
        "new_24h": new_24h,
        "new_7d": new_7d,
        "users": page_items,
        "page": page,
        "page_size": page_size,
        "has_more": end < len(enriched),
    }


def payments_summary() -> Dict[str, Any]:
    payments = get_all_payments()
    now = int(time.time())
    day_ago = now - 24 * 3600
    week_ago = now - 7 * 24 * 3600
    month_ago = now - 30 * 24 * 3600

    total_sum = sum(p.get("amount", 0) for p in payments)
    sum_24h = sum(p.get("amount", 0) for p in payments if _parse_ts(p.get("timestamp")) >= day_ago)
    sum_7d = sum(p.get("amount", 0) for p in payments if _parse_ts(p.get("timestamp")) >= week_ago)
    sum_30d = sum(p.get("amount", 0) for p in payments if _parse_ts(p.get("timestamp")) >= month_ago)

    latest = payments[:20]

    return {
        "total_sum": total_sum,
        "sum_24h": sum_24h,
        "sum_7d": sum_7d,
        "sum_30d": sum_30d,
        "latest": latest,
    }


def stats_summary() -> Dict[str, Any]:
    history = load_json_file(GENERATIONS_HISTORY_FILE, {})
    now = int(time.time())
    day_ago = now - 24 * 3600

    success_24h = 0
    error_24h = 0
    model_counts: Dict[str, int] = {}

    for user_key, gens in history.items():
        for rec in gens:
            ts = _parse_ts(rec.get("timestamp"))
            if ts < day_ago:
                continue
            state = str(rec.get("state", "success")).lower()
            if state in {"success", "ok", "completed"} or rec.get("result_urls"):
                success_24h += 1
            else:
                error_24h += 1
            mid = rec.get("model_id") or rec.get("model")
            if mid:
                model_counts[mid] = model_counts.get(mid, 0) + 1

    top_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "success_24h": success_24h,
        "error_24h": error_24h,
        "top_models": top_models,
    }


def export_csv() -> Tuple[io.BytesIO, io.BytesIO]:
    # Users CSV
    users_data = load_json_file(USER_REGISTRY_FILE, {})
    users_buf = io.BytesIO()
    users_writer = csv.writer(io.TextIOWrapper(users_buf, encoding="utf-8", newline=""))
    users_writer.writerow(["user_id", "username", "first_name", "last_name", "updated_at"])
    for uid, rec in users_data.items():
        users_writer.writerow([
            uid,
            rec.get("username", ""),
            rec.get("first_name", ""),
            rec.get("last_name", ""),
            rec.get("updated_at", ""),
        ])
    users_buf.seek(0)

    # Payments CSV
    payments_data = load_json_file(PAYMENTS_FILE, {})
    payments_buf = io.BytesIO()
    payments_writer = csv.writer(io.TextIOWrapper(payments_buf, encoding="utf-8", newline=""))
    payments_writer.writerow(["id", "user_id", "amount", "timestamp", "status"])
    for pid, rec in payments_data.items():
        payments_writer.writerow([
            pid,
            rec.get("user_id", ""),
            rec.get("amount", 0),
            rec.get("timestamp", ""),
            rec.get("status", ""),
        ])
    payments_buf.seek(0)

    return users_buf, payments_buf
