from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncpg

from app.pricing.free_policy import get_free_daily_limit
from app.storage.postgres_storage import PostgresStorage

logger = logging.getLogger(__name__)

STATUS_OK = "OK"
STATUS_DEGRADED = "DEGRADED"
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
    return json.dumps(report, ensure_ascii=False, separators=(",", ":"))


def format_billing_preflight_report(report: Dict[str, Any]) -> str:
    sections = report.get("sections", {})
    def _line(name: str, section_key: str, suffix: str = "") -> str:
        section = sections.get(section_key, {})
        status = section.get("status", STATUS_DEGRADED)
        meta = section.get("meta", {})
        details = section.get("details", "")
        if suffix:
            suffix = f" {suffix}"
        return f"{name}: {status} {details}{suffix}".strip()

    lines = [
        "BILLING PREFLIGHT (db-only)",
        _line("DB", "db", f"(lat={sections.get('db', {}).get('meta', {}).get('latency_ms', 'n/a')}ms)"),
        _line("PARTNERS", "tenants"),
        _line("BALANCES", "balances"),
        _line("FREE_LIMITS", "free_limits"),
        _line("ATTEMPTS", "attempts"),
        _line("STORAGE_RW", "storage_rw", f"(lat={sections.get('storage_rw', {}).get('meta', {}).get('latency_ms', 'n/a')}ms)"),
        f"RESULT: {report.get('result', RESULT_DEGRADED)}",
    ]
    how_to_fix = report.get("how_to_fix") or []
    if how_to_fix:
        lines.append("HOW TO FIX:")
        for hint in how_to_fix:
            lines.append(f"- {hint}")
    return "\n".join(lines)


async def _persist_preflight_report(storage: Any, report: Dict[str, Any]) -> None:
    if storage is None:
        return
    try:
        await storage.write_json_file(_BILLING_PREFLIGHT_KEY, report)
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
    if hasattr(storage, "dsn"):
        diagnostic_storage = PostgresStorage(storage.dsn, partner_id="diagnostics")

    filename = f"_diagnostics/{bot_instance_id or 'unknown'}/billing_preflight.json"
    payload = {"nonce": os.urandom(6).hex(), "ts": int(time.time())}
    start = time.monotonic()
    try:
        await diagnostic_storage.write_json_file(filename, payload)
        loaded = await diagnostic_storage.read_json_file(filename, default={})
        rw_ok = loaded.get("nonce") == payload["nonce"]
    except Exception as exc:
        return _Section(STATUS_FAIL, f"rw failed ({str(exc)[:60]})", {"rw_ok": False})

    delete_ok = False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM storage_json WHERE partner_id=$1 AND filename=$2",
                "diagnostics",
                filename,
            )
        delete_ok = True
    except Exception as exc:
        logger.warning("BILLING_PREFLIGHT storage delete failed: %s", exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    status = STATUS_OK if rw_ok else STATUS_FAIL
    details = "ok" if rw_ok else "rw mismatch"
    meta = {"rw_ok": rw_ok, "delete_ok": delete_ok, "latency_ms": latency_ms}
    return _Section(status, details, meta)


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

            total_balance_records = await conn.fetchval(
                "/* billing_preflight:balances_total */ "
                "SELECT COALESCE(SUM(jsonb_object_length(payload)),0) "
                "FROM storage_json WHERE filename=$1",
                balances_file,
            )
            partners_with_balances = await conn.fetchval(
                "/* billing_preflight:balances_partners */ "
                "SELECT COUNT(*) FROM storage_json "
                "WHERE filename=$1 AND jsonb_object_length(payload) > 0",
                balances_file,
            )
            balances_updated_24h = await conn.fetchval(
                "/* billing_preflight:balances_updated_24h */ "
                "SELECT COUNT(*) FROM storage_json "
                "WHERE filename=$1 AND updated_at >= now() - interval '24 hours'",
                balances_file,
            )
            negative_balances = await conn.fetchval(
                "/* billing_preflight:balances_negative */ "
                "SELECT COALESCE(SUM(CASE "
                "WHEN value ~ '^-?\\d+(\\.\\d+)?$' AND value::numeric < 0 THEN 1 ELSE 0 END),0) "
                "FROM storage_json s, jsonb_each_text(s.payload) "
                "WHERE s.filename=$1",
                balances_file,
            )

            total_free_records = await conn.fetchval(
                "/* billing_preflight:free_total */ "
                "SELECT COALESCE(SUM(jsonb_object_length(payload)),0) "
                "FROM storage_json WHERE filename=$1",
                free_file,
            )
            partners_with_free = await conn.fetchval(
                "/* billing_preflight:free_partners */ "
                "SELECT COUNT(*) FROM storage_json "
                "WHERE filename=$1 AND jsonb_object_length(payload) > 0",
                free_file,
            )
            free_range = await conn.fetchrow(
                "/* billing_preflight:free_range */ "
                "SELECT "
                "MIN(CASE WHEN value ~ '^\\d+$' THEN value::int END) AS min_used, "
                "MAX(CASE WHEN value ~ '^\\d+$' THEN value::int END) AS max_used "
                "FROM storage_json s, jsonb_each_text(s.payload) "
                "WHERE s.filename=$1",
                free_file,
            )
            free_limit = get_free_daily_limit()
            free_violations = await conn.fetchval(
                "/* billing_preflight:free_violations */ "
                "SELECT COALESCE(SUM(CASE "
                "WHEN value ~ '^\\d+$' AND value::int > $2 THEN 1 ELSE 0 END),0) "
                "FROM storage_json s, jsonb_each_text(s.payload) "
                "WHERE s.filename=$1",
                free_file,
                free_limit,
            )

            total_attempts = await conn.fetchval(
                "/* billing_preflight:attempts_total */ "
                "SELECT COALESCE(SUM(jsonb_object_length(payload)),0) "
                "FROM storage_json WHERE filename=$1",
                payments_file,
            )
            attempts_last_24h = await conn.fetchval(
                "/* billing_preflight:attempts_last_24h */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload) AS e(key, value) "
                "WHERE s.filename=$1 "
                "AND (value->>'created_at') IS NOT NULL "
                "AND (value->>'created_at') <> '' "
                "AND (value->>'created_at')::timestamptz >= now() - interval '24 hours'",
                payments_file,
            )
            request_id_rows = await conn.fetchval(
                "/* billing_preflight:request_id_present */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload) AS e(key, value) "
                "WHERE s.filename=$1 AND value ? 'request_id'",
                payments_file,
            )
            duplicate_request_id = 0
            if request_id_rows:
                duplicate_request_id = await conn.fetchval(
                    "/* billing_preflight:request_id_duplicates */ "
                    "WITH reqs AS ("
                    "SELECT value->>'request_id' AS request_id "
                    "FROM storage_json s, jsonb_each(s.payload) AS e(key, value) "
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
            stale_pending = await conn.fetchval(
                "/* billing_preflight:stale_pending */ "
                "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload) AS e(key, value) "
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
            tenants_status = STATUS_FAIL
            tenants_details = f"missing_partner_id={int(missing_partner_rows)}"
        elif partner_id and not partner_present and partners_found:
            tenants_status = STATUS_FAIL
            tenants_details = "tenant isolation mismatch"

        balances_status = STATUS_OK
        balances_details = (
            f"records={int(total_balance_records)}, partners={int(partners_with_balances)}, "
            f"neg={int(negative_balances)}, updated24h={int(balances_updated_24h)}"
        )
        if total_balance_records == 0:
            balances_details += " (initialized=0)"
        if negative_balances:
            balances_status = STATUS_FAIL

        free_status = STATUS_OK
        free_details = (
            f"records={int(total_free_records)}, partners={int(partners_with_free)}, "
            f"violations={int(free_violations)}, "
            f"used_today_range={free_range['min_used']}-{free_range['max_used']}"
        )
        if total_free_records == 0:
            free_details += " (initialized=0)"
        if free_violations:
            free_status = STATUS_DEGRADED

        attempts_status = STATUS_OK
        attempts_details = (
            f"total={int(total_attempts)}, last24h={int(attempts_last_24h)}, "
            f"dup_request_id={int(duplicate_request_id)}, stale_pending={int(stale_pending)}"
        )
        if not request_id_rows:
            attempts_details += " (request_id=not_tracked)"
        if duplicate_request_id:
            attempts_status = STATUS_FAIL
        if stale_pending:
            attempts_status = STATUS_DEGRADED if attempts_status != STATUS_FAIL else attempts_status

        storage_rw_section = await _storage_rw_smoke(storage, pool, bot_instance_id=partner_id)

        report["sections"] = {
            "db": {"status": db_section.status, "details": db_section.details, "meta": db_section.meta},
            "tenants": {"status": tenants_status, "details": tenants_details, "meta": tenant_meta},
            "balances": {"status": balances_status, "details": balances_details, "meta": {}},
            "free_limits": {"status": free_status, "details": free_details, "meta": {"daily_limit": free_limit}},
            "attempts": {"status": attempts_status, "details": attempts_details, "meta": {"stale_minutes": stale_minutes}},
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
        report["result"] = RESULT_READY if overall == STATUS_OK else RESULT_DEGRADED if overall == STATUS_DEGRADED else RESULT_FAIL

        how_to_fix: List[str] = []
        if tenants_status == STATUS_FAIL:
            how_to_fix.append("Verify BOT_INSTANCE_ID and tenant rows in storage_json.")
        if balances_status == STATUS_FAIL:
            how_to_fix.append("Investigate negative balances; audit balance deductions and storage consistency.")
        if free_status == STATUS_DEGRADED and free_violations:
            how_to_fix.append("Check free usage counters; reset or adjust daily limits if needed.")
        if attempts_status == STATUS_FAIL:
            how_to_fix.append("Investigate duplicate request_id entries in payments.")
        if attempts_status == STATUS_DEGRADED and stale_pending:
            how_to_fix.append("Review pending payments older than threshold; clean up if safe.")
        if storage_rw_section.status == STATUS_FAIL:
            how_to_fix.append("Verify diagnostics tenant access for storage_json.")
        report["how_to_fix"] = how_to_fix

    except Exception as exc:
        logger.error("BILLING_PREFLIGHT failed: %s", exc, exc_info=True)
        report["sections"]["db"] = {
            "status": STATUS_FAIL,
            "details": f"query failed ({str(exc)[:80]})",
            "meta": {},
        }
        report["result"] = RESULT_FAIL
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
