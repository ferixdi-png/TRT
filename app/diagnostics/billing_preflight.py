from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import asyncpg

from app.diagnostics.sql_helpers import (
    AggregateResult,
    STATUS_ERROR,
    STATUS_OK as SQL_STATUS_OK,
    STATUS_UNKNOWN as SQL_STATUS_UNKNOWN,
    count_payload_entries,
    count_payload_nonempty,
    fetch_column_type,
    merge_status,
    run_row,
    run_scalar,
)
from app.pricing.free_policy import get_free_daily_limit
from app.storage.postgres_storage import PostgresStorage

logger = logging.getLogger(__name__)

STATUS_OK = "OK"
STATUS_DEGRADED = "DEGRADED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_FAIL = "FAIL"

RESULT_READY = "READY"
RESULT_DEGRADED = "DEGRADED"
RESULT_FAIL = "FAIL"

_BILLING_PREFLIGHT_KEY = "_diagnostics/billing_preflight.json"
_cached_billing_preflight: Optional[Dict[str, Any]] = None
_cached_billing_preflight_text: Optional[str] = None


@dataclass
class _Section:
    status: str
    details: str
    meta: Dict[str, Any]


def _mask_partner_id(partner_id: str) -> str:
    if not partner_id:
        return "missing"
    if len(partner_id) <= 3:
        return f"{partner_id[0]}***"
    return f"{partner_id[0]}***{partner_id[-2:]}"


def _hash_sample(partner_id: str) -> str:
    digest = hashlib.sha256(partner_id.encode("utf-8")).hexdigest()[:6]
    return f"{_mask_partner_id(partner_id)}#{digest}"


def _cache_billing_preflight(report: Dict[str, Any], human: str) -> None:
    global _cached_billing_preflight, _cached_billing_preflight_text
    _cached_billing_preflight = report
    _cached_billing_preflight_text = human


def get_cached_billing_preflight() -> Optional[Dict[str, Any]]:
    return _cached_billing_preflight


def get_cached_billing_preflight_text() -> Optional[str]:
    return _cached_billing_preflight_text


def _build_report_json(report: Dict[str, Any]) -> str:
    return json.dumps(_json_safe(report), ensure_ascii=False, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    return value


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("BILLING_PREFLIGHT invalid %s=%s, using %s", name, raw, default)
        return default


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("BILLING_PREFLIGHT invalid %s=%s, using %s", name, raw, default)
        return default


def format_billing_preflight_report(report: Dict[str, Any]) -> str:
    sections = report.get("sections", {})
    db_meta = sections.get("db", {}).get("meta", {})
    storage_meta = sections.get("storage_rw", {}).get("meta", {})
    tenants_meta = sections.get("tenants", {}).get("meta", {})
    balances_meta = sections.get("balances", {}).get("meta", {})
    free_meta = sections.get("free_limits", {}).get("meta", {})
    attempts_meta = sections.get("attempts", {}).get("meta", {})

    lines = [
        "BILLING PREFLIGHT (db-only)",
        f"DB: {sections.get('db', {}).get('status', STATUS_DEGRADED)} (lat={db_meta.get('latency_ms', 'n/a')}ms)",
        (
            "PARTNERS: "
            f"found={tenants_meta.get('partners_found', 'n/a')} "
            f"(sample {tenants_meta.get('partners_sample', [])})"
        ),
        (
            "BALANCES: "
            f"records={balances_meta.get('records', 'n/a')} "
            f"status={sections.get('balances', {}).get('status', STATUS_UNKNOWN)}"
            f"{balances_meta.get('note', '')}"
        ),
        (
            "FREE_LIMITS: "
            f"records={free_meta.get('records', 'n/a')} "
            f"status={sections.get('free_limits', {}).get('status', STATUS_UNKNOWN)}"
            f"{free_meta.get('note', '')}"
        ),
        (
            "ATTEMPTS: "
            f"last24h={attempts_meta.get('last24h', 'n/a')} "
            f"dup={attempts_meta.get('dup_request_id', 'n/a')} "
            f"status={sections.get('attempts', {}).get('status', STATUS_UNKNOWN)}"
            f"{attempts_meta.get('note', '')}"
        ),
        f"STORAGE_RW: {sections.get('storage_rw', {}).get('status', STATUS_DEGRADED)} (lat={storage_meta.get('latency_ms', 'n/a')}ms)",
        f"RESULT: {report.get('result', RESULT_DEGRADED)}",
    ]
    return "\n".join(lines)


async def _persist_preflight_report(storage: Any, report: Dict[str, Any]) -> None:
    if storage is None:
        return
    try:
        await storage.write_json_file(_BILLING_PREFLIGHT_KEY, _json_safe(report))
    except Exception as exc:
        logger.warning("BILLING_PREFLIGHT persist failed: %s", exc)


async def _resolve_pool(storage: Any, db_pool: Optional[asyncpg.Pool]) -> tuple[asyncpg.Pool, bool]:
    if db_pool is not None:
        return db_pool, False
    if storage and hasattr(storage, "_get_pool") and asyncio.iscoroutinefunction(storage._get_pool):
        return await storage._get_pool(), False
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL missing for billing preflight")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1)
    return pool, True


def _section_status(sections: List[_Section]) -> str:
    if any(section.status == STATUS_FAIL for section in sections):
        return STATUS_FAIL
    if any(section.status == STATUS_DEGRADED for section in sections):
        return STATUS_DEGRADED
    if any(section.status == STATUS_UNKNOWN for section in sections):
        return STATUS_DEGRADED
    return STATUS_OK


async def _storage_rw_smoke(
    storage: Any,
    db_pool: asyncpg.Pool,
    *,
    bot_instance_id: str,
) -> _Section:
    if storage is None:
        return _Section(STATUS_FAIL, "storage unavailable", {"rw_ok": False})

    diagnostic_storage = storage
    diagnostics_source = "primary"
    diagnostics_init_error: Optional[str] = None
    if hasattr(storage, "diagnostics_storage"):
        diagnostic_storage = getattr(storage, "diagnostics_storage") or storage
        diagnostics_source = "custom"
    elif hasattr(storage, "get_diagnostics_storage"):
        try:
            diagnostic_storage = storage.get_diagnostics_storage()
            diagnostics_source = "custom"
        except Exception as exc:
            diagnostics_init_error = str(exc)[:120]
            diagnostic_storage = storage
    elif hasattr(storage, "dsn"):
        try:
            diagnostic_storage = PostgresStorage(storage.dsn, partner_id="diagnostics")
            diagnostics_source = "postgres"
        except Exception as exc:
            diagnostics_init_error = str(exc)[:120]
            diagnostic_storage = storage

    timeout_s = _read_float_env("BILLING_PREFLIGHT_STORAGE_TIMEOUT_S", 2.0)
    retries = max(1, _read_int_env("BILLING_PREFLIGHT_STORAGE_RETRIES", 2))

    filename = f"_diagnostics/{bot_instance_id or 'unknown'}/billing_preflight.json"
    payload = {"nonce": os.urandom(6).hex(), "ts": int(time.time())}
    start = time.monotonic()

    async def _attempt_rw(target_storage: Any) -> tuple[bool, Optional[str]]:
        last_error: Optional[str] = None
        for attempt in range(1, retries + 1):
            try:
                await asyncio.wait_for(target_storage.write_json_file(filename, payload), timeout=timeout_s)
                loaded = await asyncio.wait_for(target_storage.read_json_file(filename, default={}), timeout=timeout_s)
                if loaded.get("nonce") == payload["nonce"]:
                    return True, None
                last_error = "rw mismatch"
            except Exception as exc:
                last_error = str(exc)[:120]
            if attempt < retries:
                await asyncio.sleep(0.05)
        return False, last_error

    rw_ok, primary_error = await _attempt_rw(diagnostic_storage)

    delete_ok = False
    partner_for_delete = getattr(diagnostic_storage, "partner_id", "diagnostics")
    if rw_ok:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM storage_json WHERE partner_id=$1 AND filename=$2",
                    partner_for_delete,
                    filename,
                )
            delete_ok = True
        except Exception as exc:
            logger.warning("BILLING_PREFLIGHT storage delete failed: %s", exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    if rw_ok:
        status = STATUS_OK
        details = "ok"
        meta = {
            "rw_ok": True,
            "delete_ok": delete_ok,
            "latency_ms": latency_ms,
            "diagnostics_source": diagnostics_source,
            "timeout_s": timeout_s,
            "retries": retries,
        }
        if diagnostics_init_error:
            meta["diagnostics_init_error"] = diagnostics_init_error
        return _Section(status, details, meta)

    if diagnostic_storage is not storage:
        logger.warning(
            "BILLING_PREFLIGHT storage_rw diagnostics failed code=BPF_STORAGE_RW_DIAGNOSTICS_FAILED error=%s",
            primary_error,
        )
        fallback_start = time.monotonic()
        fallback_ok, fallback_error = await _attempt_rw(storage)
        fallback_latency_ms = int((time.monotonic() - fallback_start) * 1000)
        if fallback_ok:
            fallback_partner = getattr(storage, "partner_id", bot_instance_id or "unknown")
            try:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM storage_json WHERE partner_id=$1 AND filename=$2",
                        fallback_partner,
                        filename,
                    )
                delete_ok = True
            except Exception as exc:
                logger.warning("BILLING_PREFLIGHT storage delete failed: %s", exc)
            meta = {
                "rw_ok": True,
                "delete_ok": delete_ok,
                "latency_ms": fallback_latency_ms,
                "fallback_used": True,
                "primary_error": primary_error,
                "diagnostics_source": diagnostics_source,
                "timeout_s": timeout_s,
                "retries": retries,
                "error_code": "BPF_STORAGE_RW_DIAGNOSTICS_FAILED",
            }
            return _Section(STATUS_DEGRADED, "rw ok on tenant fallback", meta)
        logger.error(
            "BILLING_PREFLIGHT storage_rw fallback failed code=BPF_STORAGE_RW_FALLBACK_FAILED error=%s",
            fallback_error,
        )
        meta = {
            "rw_ok": False,
            "delete_ok": False,
            "latency_ms": fallback_latency_ms,
            "fallback_used": True,
            "primary_error": primary_error,
            "fallback_error": fallback_error,
            "diagnostics_source": diagnostics_source,
            "timeout_s": timeout_s,
            "retries": retries,
            "error_code": "BPF_STORAGE_RW_FALLBACK_FAILED",
        }
        return _Section(STATUS_FAIL, f"rw failed ({fallback_error or primary_error})", meta)

    details = "rw mismatch" if primary_error == "rw mismatch" else f"rw failed ({primary_error})"
    meta = {
        "rw_ok": False,
        "delete_ok": False,
        "latency_ms": latency_ms,
        "diagnostics_source": diagnostics_source,
        "timeout_s": timeout_s,
        "retries": retries,
        "error_code": "BPF_STORAGE_RW_FAILED",
    }
    if diagnostics_init_error:
        meta["diagnostics_init_error"] = diagnostics_init_error
    return _Section(STATUS_FAIL, details, meta)


async def run_billing_preflight(
    storage: Any,
    db_pool: Optional[asyncpg.Pool],
    *,
    max_partners: int = 50,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "sections": {},
        "result": RESULT_DEGRADED,
        "how_to_fix": [],
    }

    pool: Optional[asyncpg.Pool] = None
    created_pool = False
    try:
        pool, created_pool = await _resolve_pool(storage, db_pool)
    except Exception as exc:
        report["sections"]["db"] = {
            "status": STATUS_FAIL,
            "details": f"db connect failed ({str(exc)[:80]})",
            "meta": {"latency_ms": None},
        }
        report["result"] = RESULT_FAIL
        report["how_to_fix"] = [
            "Verify DATABASE_URL and database availability.",
            "Ensure Postgres schema is reachable from the bot container.",
        ]
        human = format_billing_preflight_report(report)
        logger.info("BILLING_PREFLIGHT %s", _build_report_json(report))
        logger.info("%s", human)
        _cache_billing_preflight(report, human)
        return report

    try:
        async with pool.acquire() as conn:
            db_start = time.monotonic()
            await conn.execute("/* billing_preflight:db_ping */ SELECT 1")
            db_latency_ms = int((time.monotonic() - db_start) * 1000)

            partners_found = await conn.fetchval(
                "/* billing_preflight:partners_count */ SELECT COUNT(DISTINCT partner_id) FROM storage_json"
            )
            partner_rows = await conn.fetch(
                "/* billing_preflight:partners_sample */ "
                "SELECT DISTINCT partner_id FROM storage_json ORDER BY partner_id LIMIT 3"
            )
            partners_sample = [_hash_sample(row["partner_id"]) for row in partner_rows if row["partner_id"]]
            top_rows = await conn.fetch(
                "/* billing_preflight:partners_top */ "
                "SELECT partner_id, COUNT(*) AS file_count "
                "FROM storage_json GROUP BY partner_id ORDER BY file_count DESC LIMIT $1",
                max_partners,
            )
            partners_top = [
                {"partner": _hash_sample(row["partner_id"]), "file_count": int(row["file_count"])}
                for row in top_rows
                if row["partner_id"]
            ]
            missing_partner_rows = await conn.fetchval(
                "/* billing_preflight:partners_missing */ "
                "SELECT COUNT(*) FROM storage_json WHERE partner_id IS NULL OR btrim(partner_id) = ''"
            )

            partner_id = (getattr(storage, "partner_id", "") or os.getenv("BOT_INSTANCE_ID", "")).strip()
            partner_present = None
            if partner_id:
                partner_present = await conn.fetchval(
                    "/* billing_preflight:partner_present */ "
                    "SELECT 1 FROM storage_json WHERE partner_id=$1 LIMIT 1",
                    partner_id,
                )

            balances_file = getattr(storage, "balances_file", "user_balances.json")
            free_file = getattr(storage, "free_generations_file", "daily_free_generations.json")
            payments_file = getattr(storage, "payments_file", "payments.json")

            payload_type = await fetch_column_type(conn, "storage_json", "payload")

            total_balance_records = await count_payload_entries(
                conn, balances_file, column_type=payload_type, key="balances_total"
            )
            partners_with_balances = await count_payload_nonempty(
                conn, balances_file, column_type=payload_type, key="balances_partners"
            )
            balances_updated_24h = await run_scalar(
                conn,
                "balances_updated_24h",
                "/* billing_preflight:balances_updated_24h */ "
                "SELECT COUNT(*) FROM storage_json "
                "WHERE filename=$1 AND updated_at >= now() - interval '24 hours'",
                balances_file,
            )
            negative_balances = await run_scalar(
                conn,
                "balances_negative",
                "/* billing_preflight:balances_negative */ "
                "SELECT COALESCE(SUM(CASE "
                "WHEN value ~ '^-?\\d+(\\.\\d+)?$' AND value::numeric < 0 THEN 1 ELSE 0 END),0) "
                "FROM storage_json s, jsonb_each_text(s.payload::jsonb) "
                "WHERE s.filename=$1",
                balances_file,
            )

            total_free_records = await count_payload_entries(
                conn, free_file, column_type=payload_type, key="free_total"
            )
            partners_with_free = await count_payload_nonempty(
                conn, free_file, column_type=payload_type, key="free_partners"
            )
            free_range = await run_row(
                conn,
                "free_range",
                "/* billing_preflight:free_range */ "
                "SELECT "
                "MIN(CASE WHEN value ~ '^\\d+$' THEN value::int END) AS min_used, "
                "MAX(CASE WHEN value ~ '^\\d+$' THEN value::int END) AS max_used "
                "FROM storage_json s, jsonb_each_text(s.payload::jsonb) "
                "WHERE s.filename=$1",
                free_file,
            )
            free_limit = get_free_daily_limit()
            free_violations = await run_scalar(
                conn,
                "free_violations",
                "/* billing_preflight:free_violations */ "
                "SELECT COALESCE(SUM(CASE "
                "WHEN value ~ '^\\d+$' AND value::int > $2 THEN 1 ELSE 0 END),0) "
                "FROM storage_json s, jsonb_each_text(s.payload::jsonb) "
                "WHERE s.filename=$1",
                free_file,
                free_limit,
            )

            total_attempts = await count_payload_entries(
                conn, payments_file, column_type=payload_type, key="attempts_total"
            )
            attempts_last_24h = await run_scalar(
                conn,
                "attempts_last_24h",
                "/* billing_preflight:attempts_last_24h */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload::jsonb) AS e(key, value) "
                "WHERE s.filename=$1 "
                "AND (value->>'created_at') IS NOT NULL "
                "AND (value->>'created_at') <> '' "
                "AND (value->>'created_at')::timestamptz >= now() - interval '24 hours'",
                payments_file,
            )
            request_id_rows = await run_scalar(
                conn,
                "request_id_present",
                "/* billing_preflight:request_id_present */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload::jsonb) AS e(key, value) "
                "WHERE s.filename=$1 AND value ? 'request_id'",
                payments_file,
            )
            duplicate_request_id = AggregateResult(value=0, status=SQL_STATUS_OK, note="")
            if request_id_rows.status == SQL_STATUS_OK and request_id_rows.value:
                duplicate_request_id = await run_scalar(
                    conn,
                    "request_id_duplicates",
                    "/* billing_preflight:request_id_duplicates */ "
                    "WITH reqs AS ("
                    "SELECT value->>'request_id' AS request_id "
                    "FROM storage_json s, jsonb_each(s.payload::jsonb) AS e(key, value) "
                    "WHERE s.filename=$1 AND value ? 'request_id'"
                    ") "
                    "SELECT COALESCE(SUM(cnt - 1),0) FROM ("
                    "SELECT request_id, COUNT(*) AS cnt "
                    "FROM reqs WHERE request_id IS NOT NULL AND request_id <> '' "
                    "GROUP BY request_id HAVING COUNT(*) > 1"
                    ") AS dup",
                    payments_file,
                )

            stale_minutes = 30
            stale_pending = await run_scalar(
                conn,
                "stale_pending",
                "/* billing_preflight:stale_pending */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload::jsonb) AS e(key, value) "
                "WHERE s.filename=$1 "
                "AND value->>'status' = 'pending' "
                "AND (value->>'created_at') IS NOT NULL "
                "AND (value->>'created_at') <> '' "
                "AND (value->>'created_at')::timestamptz < now() - ($2::int || ' minutes')::interval",
                payments_file,
                stale_minutes,
            )

        db_section = _Section(STATUS_OK, "ok", {"latency_ms": db_latency_ms})

        tenants_status = STATUS_OK
        tenants_details = f"found={int(partners_found)}, sample={partners_sample}"
        tenant_meta = {
            "partners_found": int(partners_found),
            "partners_sample": partners_sample,
            "partners_top": partners_top[: min(3, len(partners_top))],
            "storage_partner": _mask_partner_id(partner_id),
        }
        if missing_partner_rows:
            tenants_status = STATUS_DEGRADED
            tenants_details = f"missing_partner_id={int(missing_partner_rows)}"
        elif partner_id and not partner_present and partners_found:
            tenants_status = STATUS_DEGRADED
            tenants_details = "tenant isolation mismatch"

        balances_status = STATUS_OK
        balances_note = ""
        balances_merge = merge_status(
            total_balance_records,
            partners_with_balances,
            balances_updated_24h,
            negative_balances,
        )
        if balances_merge in {STATUS_ERROR, SQL_STATUS_UNKNOWN}:
            balances_status = STATUS_UNKNOWN
            balances_note = f" ({total_balance_records.note or 'aggregate_compat'})"
        balances_details = (
            f"records={total_balance_records.value if total_balance_records.value is not None else 'n/a'}, "
            f"partners={partners_with_balances.value if partners_with_balances.value is not None else 'n/a'}, "
            f"neg={negative_balances.value if negative_balances.value is not None else 'n/a'}, "
            f"updated24h={balances_updated_24h.value if balances_updated_24h.value is not None else 'n/a'}"
        )
        if total_balance_records.value == 0:
            balances_details += " (initialized=0)"
        if negative_balances.status == SQL_STATUS_OK and negative_balances.value:
            balances_status = STATUS_DEGRADED
            balances_note = " (negative balances)"

        free_status = STATUS_OK
        free_note = ""
        free_merge = merge_status(total_free_records, partners_with_free, free_range, free_violations)
        if free_merge in {STATUS_ERROR, SQL_STATUS_UNKNOWN}:
            free_status = STATUS_UNKNOWN
            free_note = f" ({total_free_records.note or 'aggregate_compat'})"
        free_details = (
            f"records={total_free_records.value if total_free_records.value is not None else 'n/a'}, "
            f"partners={partners_with_free.value if partners_with_free.value is not None else 'n/a'}, "
            f"violations={free_violations.value if free_violations.value is not None else 'n/a'}, "
            f"used_today_range="
            f"{(free_range.value or {}).get('min_used')}-{(free_range.value or {}).get('max_used')}"
        )
        if total_free_records.value == 0:
            free_details += " (initialized=0)"
        if free_violations.status == SQL_STATUS_OK and free_violations.value:
            free_status = STATUS_DEGRADED
            free_note = " (violations)"

        attempts_status = STATUS_OK
        attempts_note = ""
        attempts_merge = merge_status(
            total_attempts,
            attempts_last_24h,
            request_id_rows,
            duplicate_request_id,
            stale_pending,
        )
        if attempts_merge in {STATUS_ERROR, SQL_STATUS_UNKNOWN}:
            attempts_status = STATUS_UNKNOWN
            attempts_note = f" ({total_attempts.note or 'aggregate_compat'})"
        attempts_details = (
            f"total={total_attempts.value if total_attempts.value is not None else 'n/a'}, "
            f"last24h={attempts_last_24h.value if attempts_last_24h.value is not None else 'n/a'}, "
            f"dup_request_id={duplicate_request_id.value if duplicate_request_id.value is not None else 'n/a'}, "
            f"stale_pending={stale_pending.value if stale_pending.value is not None else 'n/a'}"
        )
        if request_id_rows.status == SQL_STATUS_OK and not request_id_rows.value:
            attempts_details += " (request_id=not_tracked)"
        if duplicate_request_id.status == SQL_STATUS_OK and duplicate_request_id.value:
            attempts_status = STATUS_DEGRADED
            attempts_note = " (dup_request_id)"
        if stale_pending.status == SQL_STATUS_OK and stale_pending.value:
            attempts_status = STATUS_DEGRADED if attempts_status != STATUS_UNKNOWN else attempts_status
            attempts_note = " (stale_pending)"

        storage_rw_section = await _storage_rw_smoke(storage, pool, bot_instance_id=partner_id)

        report["sections"] = {
            "db": {"status": db_section.status, "details": db_section.details, "meta": db_section.meta},
            "tenants": {"status": tenants_status, "details": tenants_details, "meta": tenant_meta},
            "balances": {
                "status": balances_status,
                "details": balances_details,
                "meta": {"records": total_balance_records.value, "note": balances_note},
            },
            "free_limits": {
                "status": free_status,
                "details": free_details,
                "meta": {"daily_limit": free_limit, "records": total_free_records.value, "note": free_note},
            },
            "attempts": {
                "status": attempts_status,
                "details": attempts_details,
                "meta": {
                    "stale_minutes": stale_minutes,
                    "last24h": attempts_last_24h.value,
                    "dup_request_id": duplicate_request_id.value,
                    "note": attempts_note,
                },
            },
            "storage_rw": {
                "status": storage_rw_section.status,
                "details": storage_rw_section.details,
                "meta": storage_rw_section.meta,
            },
        }

        overall = _section_status(
            [
                db_section,
                _Section(tenants_status, tenants_details, {}),
                _Section(balances_status, balances_details, {}),
                _Section(free_status, free_details, {}),
                _Section(attempts_status, attempts_details, {}),
                storage_rw_section,
            ]
        )
        if db_section.status == STATUS_FAIL or storage_rw_section.status == STATUS_FAIL:
            report["result"] = RESULT_FAIL
        else:
            report["result"] = RESULT_READY if overall == STATUS_OK else RESULT_DEGRADED

        how_to_fix: List[str] = []
        if tenants_status == STATUS_DEGRADED:
            how_to_fix.append("Verify BOT_INSTANCE_ID and tenant rows in storage_json.")
        if balances_status == STATUS_DEGRADED:
            how_to_fix.append("Review balances consistency; check negative balances or stale updates.")
        if free_status == STATUS_DEGRADED and free_violations.status == SQL_STATUS_OK and free_violations.value:
            how_to_fix.append("Check free usage counters; reset or adjust daily limits if needed.")
        if attempts_status == STATUS_DEGRADED and stale_pending.status == SQL_STATUS_OK and stale_pending.value:
            how_to_fix.append("Review pending payments older than threshold; clean up if safe.")
        if storage_rw_section.status == STATUS_FAIL:
            how_to_fix.append("Verify diagnostics tenant access for storage_json.")
        report["how_to_fix"] = how_to_fix

    except Exception as exc:
        logger.debug("BILLING_PREFLIGHT failed: %s", exc, exc_info=True)
        report["sections"]["db"] = {
            "status": STATUS_DEGRADED,
            "details": f"query failed ({str(exc)[:80]})",
            "meta": {},
        }
        report["result"] = RESULT_DEGRADED
        report["how_to_fix"] = [
            "Check storage_json schema and database permissions.",
            "Verify DATABASE_URL points to the correct Postgres instance.",
        ]
    finally:
        if created_pool and pool is not None:
            await pool.close()

    await _persist_preflight_report(storage, report)
    human = format_billing_preflight_report(report)
    logger.info("BILLING_PREFLIGHT %s", _build_report_json(report))
    logger.info("%s", human)
    _cache_billing_preflight(report, human)
    return report
