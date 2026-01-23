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


@dataclass
class _TimedQuery:
    value: Any
    status: str
    latency_ms: Optional[int]
    lat_ms: Optional[int]
    error: Optional[Dict[str, Any]] = None
    note: str = ""


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


def _describe_exception(exc: Exception) -> Dict[str, Any]:
    info: Dict[str, Any] = {"error_type": type(exc).__name__}
    message = str(exc).strip()
    if message:
        info["error"] = message[:200]
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate:
        info["sqlstate"] = sqlstate
    if isinstance(exc, asyncio.TimeoutError):
        info["timeout"] = True
    return info


def _format_latency_ms(value: Optional[Any]) -> str:
    if value is None or value == "n/a":
        return "lat_ms=n/a"
    return f"lat_ms={value}ms"


def _format_storage_reason(meta: Dict[str, Any]) -> str:
    parts: List[str] = []
    if meta.get("error_code"):
        parts.append(str(meta["error_code"]))
    if meta.get("error_type"):
        parts.append(str(meta["error_type"]))
    if meta.get("sqlstate"):
        parts.append(f"sqlstate={meta['sqlstate']}")
    if meta.get("timeout"):
        parts.append("timeout")
    if meta.get("error"):
        parts.append(str(meta["error"]))
    return "; ".join(parts)


async def _timed_query(
    func,
    *args: Any,
    default: Any = None,
) -> _TimedQuery:
    start = time.monotonic()
    try:
        value = await func(*args)
        latency_ms = int((time.monotonic() - start) * 1000)
        return _TimedQuery(value=value, status=STATUS_OK, latency_ms=latency_ms, lat_ms=latency_ms)
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error_meta = _describe_exception(exc)
        return _TimedQuery(
            value=default,
            status=STATUS_DEGRADED,
            latency_ms=latency_ms,
            lat_ms=latency_ms,
            error=error_meta,
        )


async def _timed_aggregate(func, *args: Any, **kwargs: Any) -> tuple[AggregateResult, Dict[str, Any]]:
    start = time.monotonic()
    result = await func(*args, **kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)
    status = STATUS_OK if result.status == SQL_STATUS_OK else STATUS_DEGRADED
    meta: Dict[str, Any] = {"status": status, "latency_ms": latency_ms, "lat_ms": latency_ms}
    if result.note:
        meta["note"] = result.note
    if result.error_type:
        meta["error_type"] = result.error_type
    if result.sqlstate:
        meta["sqlstate"] = result.sqlstate
    if result.timeout:
        meta["timeout"] = result.timeout
    return result, meta


def _summarize_queries(named_meta: List[tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
    status = STATUS_OK
    latency_ms: Optional[int] = None
    errors: List[Dict[str, Any]] = []
    for name, meta in named_meta:
        if not meta:
            continue
        if meta.get("status") != STATUS_OK:
            status = STATUS_DEGRADED
        meta_latency = meta.get("latency_ms", meta.get("lat_ms"))
        if meta_latency is not None:
            latency_ms = max(latency_ms or 0, int(meta_latency))
        if meta.get("status") != STATUS_OK:
            error = meta.get("error") or {}
            if error:
                errors.append({"query": name, **error})
            elif meta.get("note"):
                errors.append({"query": name, "note": meta["note"]})
    summary: Dict[str, Any] = {"query_status": status, "query_latency_ms": latency_ms}
    if errors:
        summary["query_errors"] = errors
    return summary


def _error_query_meta(exc: Exception) -> Dict[str, Any]:
    error_meta = _describe_exception(exc)
    return {
        "status": STATUS_DEGRADED,
        "latency_ms": None,
        "lat_ms": None,
        "error": error_meta,
        "error_type": error_meta.get("error_type"),
        "sqlstate": error_meta.get("sqlstate"),
        "timeout": error_meta.get("timeout", False),
    }


def _aggregate_error_result(exc: Exception, *, note: str = "section_failed") -> AggregateResult:
    error_meta = _describe_exception(exc)
    return AggregateResult(
        value=None,
        status=SQL_STATUS_UNKNOWN,
        note=error_meta.get("error") or note,
        error_type=error_meta.get("error_type"),
        sqlstate=error_meta.get("sqlstate"),
        timeout=bool(error_meta.get("timeout")),
    )


def _append_error_details(details: str, meta: Dict[str, Any]) -> str:
    errors = meta.get("query_errors") or []
    if errors:
        error_type = errors[0].get("error_type") or errors[0].get("note")
        if error_type:
            return f"{details} (error={error_type})"
    return details


def format_billing_preflight_report(report: Dict[str, Any]) -> str:
    sections = report.get("sections", {})
    db_meta = sections.get("db", {}).get("meta", {})
    storage_meta = sections.get("storage_rw", {}).get("meta", {})
    tenants_meta = sections.get("tenants", {}).get("meta", {})
    users_meta = sections.get("users", {}).get("meta", {})
    balances_meta = sections.get("balances", {}).get("meta", {})
    free_meta = sections.get("free_limits", {}).get("meta", {})
    attempts_meta = sections.get("attempts", {}).get("meta", {})
    storage_reason = _format_storage_reason(storage_meta)
    storage_reason_suffix = f" reason={storage_reason}" if storage_reason else ""

    lines = [
        "BILLING PREFLIGHT (db-only)",
        f"DB: {sections.get('db', {}).get('status', STATUS_DEGRADED)} ({_format_latency_ms(db_meta.get('latency_ms', 'n/a'))})",
        (
            "PARTNERS: "
            f"found={tenants_meta.get('partners_found', 'n/a')} "
            f"(sample {tenants_meta.get('partners_sample', [])})"
        ),
        (
            "USERS: "
            f"records={users_meta.get('records', 'n/a')} "
            f"status={sections.get('users', {}).get('status', STATUS_UNKNOWN)}"
            f"{users_meta.get('note', '')}"
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
        (
            "STORAGE_RW: "
            f"{sections.get('storage_rw', {}).get('status', STATUS_DEGRADED)} "
            f"({_format_latency_ms(storage_meta.get('latency_ms', 'n/a'))}{storage_reason_suffix})"
        ),
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

    async def _attempt_rw(target_storage: Any) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        last_error: Optional[str] = None
        last_error_meta: Optional[Dict[str, Any]] = None
        for attempt in range(1, retries + 1):
            try:
                await asyncio.wait_for(target_storage.write_json_file(filename, payload), timeout=timeout_s)
                loaded = await asyncio.wait_for(target_storage.read_json_file(filename, default={}), timeout=timeout_s)
                if not isinstance(loaded, dict):
                    normalized = None
                    if isinstance(loaded, str):
                        try:
                            normalized = json.loads(loaded)
                        except json.JSONDecodeError:
                            normalized = None
                    if isinstance(normalized, dict):
                        loaded = normalized
                    else:
                        logger.warning(
                            "BILLING_PREFLIGHT storage_rw invalid payload code=BPF_STORAGE_RW_BAD_PAYLOAD type=%s",
                            type(loaded).__name__,
                        )
                        last_error = f"invalid_payload type={type(loaded).__name__}"
                        last_error_meta = {
                            "error_type": "InvalidPayload",
                            "error": last_error,
                        }
                        continue
                if loaded.get("nonce") == payload["nonce"]:
                    return True, None, None
                last_error = "rw mismatch"
                last_error_meta = {"error_type": "Mismatch", "error": last_error}
            except Exception as exc:
                error_meta = _describe_exception(exc)
                last_error = error_meta.get("error") or error_meta.get("error_type")
                last_error_meta = error_meta
            if attempt < retries:
                await asyncio.sleep(0.05)
        return False, last_error, last_error_meta

    rw_ok, primary_error, primary_error_meta = await _attempt_rw(diagnostic_storage)

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
        fallback_ok, fallback_error, fallback_error_meta = await _attempt_rw(storage)
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
            if primary_error_meta:
                meta.update({k: v for k, v in primary_error_meta.items() if k in {"error", "error_type", "sqlstate", "timeout"}})
            return _Section(STATUS_DEGRADED, "rw ok on tenant fallback", meta)
        logger.error(
            "BILLING_PREFLIGHT storage_rw fallback failed code=BPF_STORAGE_RW_FALLBACK_FAILED error=%s",
            fallback_error,
        )
        error_code = "BPF_STORAGE_RW_FALLBACK_FAILED"
        if fallback_error and "invalid_payload" in fallback_error:
            error_code = "BPF_STORAGE_RW_BAD_PAYLOAD"
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
            "error_code": error_code,
        }
        if fallback_error_meta:
            meta.update({k: v for k, v in fallback_error_meta.items() if k in {"error", "error_type", "sqlstate", "timeout"}})
        return _Section(STATUS_FAIL, f"rw failed ({fallback_error or primary_error})", meta)

    details = "rw mismatch" if primary_error == "rw mismatch" else f"rw failed ({primary_error})"
    error_code = "BPF_STORAGE_RW_FAILED"
    if primary_error and "invalid_payload" in primary_error:
        error_code = "BPF_STORAGE_RW_BAD_PAYLOAD"
    meta = {
        "rw_ok": False,
        "delete_ok": False,
        "latency_ms": latency_ms,
        "diagnostics_source": diagnostics_source,
        "timeout_s": timeout_s,
        "retries": retries,
        "error_code": error_code,
    }
    if primary_error_meta:
        meta.update({k: v for k, v in primary_error_meta.items() if k in {"error", "error_type", "sqlstate", "timeout"}})
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
        query_retries = max(1, _read_int_env("BILLING_PREFLIGHT_QUERY_RETRIES", 2))
        query_backoff_s = _read_float_env("BILLING_PREFLIGHT_QUERY_BACKOFF_S", 0.2)

        partner_id = (getattr(storage, "partner_id", "") or os.getenv("BOT_INSTANCE_ID", "")).strip()
        balances_file = getattr(storage, "balances_file", "user_balances.json")
        languages_file = getattr(storage, "languages_file", "user_languages.json")
        free_file = getattr(storage, "free_generations_file", "daily_free_generations.json")
        payments_file = getattr(storage, "payments_file", "payments.json")
        free_limit = get_free_daily_limit()
        stale_minutes = 30

        db_ping = _TimedQuery(value=None, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        partners_found_query = _TimedQuery(value=0, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        partners_sample_query = _TimedQuery(value=[], status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        partners_top_query = _TimedQuery(value=[], status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        missing_partner_query = _TimedQuery(value=0, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        partner_present_query = _TimedQuery(value=None, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)
        payload_query = _TimedQuery(value="unknown", status=STATUS_DEGRADED, latency_ms=None, lat_ms=None)

        total_balance_records = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        total_user_records = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        partners_with_balances = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        balances_updated_24h = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        negative_balances = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        total_free_records = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        partners_with_free = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        free_range = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        free_violations = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        total_attempts = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        attempts_last_24h = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        request_id_rows = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")
        duplicate_request_id = AggregateResult(value=0, status=SQL_STATUS_OK, note="")
        stale_pending = AggregateResult(value=None, status=SQL_STATUS_UNKNOWN, note="not_run")

        total_balance_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        total_user_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        partners_with_balances_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        balances_updated_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        negative_balances_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        total_free_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        partners_with_free_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        free_range_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        free_violations_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        total_attempts_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        attempts_last_24h_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        request_id_rows_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        duplicate_request_id_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}
        stale_pending_meta: Dict[str, Any] = {"status": STATUS_DEGRADED, "latency_ms": None, "lat_ms": None}

        balances_details = "records=n/a, partners=n/a, neg=n/a, updated24h=n/a"
        users_details = "records=n/a"
        free_details = "records=n/a, partners=n/a, violations=n/a, used_today_range=n/a-n/a"
        attempts_details = "total=n/a, last24h=n/a, dup_request_id=n/a, stale_pending=n/a"

        for attempt in range(1, query_retries + 1):
            try:
                async with pool.acquire() as conn:
                    db_ping = await _timed_query(
                        conn.execute,
                        "/* billing_preflight:db_ping */ SELECT 1",
                    )

                    try:
                        partners_found_query = await _timed_query(
                            conn.fetchval,
                            "/* billing_preflight:partners_count */ SELECT COUNT(DISTINCT partner_id) FROM storage_json",
                            default=0,
                        )
                        partners_sample_query = await _timed_query(
                            conn.fetch,
                            "/* billing_preflight:partners_sample */ "
                            "SELECT DISTINCT partner_id FROM storage_json ORDER BY partner_id LIMIT 3",
                            default=[],
                        )
                        partners_top_query = await _timed_query(
                            conn.fetch,
                            "/* billing_preflight:partners_top */ "
                            "SELECT partner_id, COUNT(*) AS file_count "
                            "FROM storage_json GROUP BY partner_id ORDER BY file_count DESC LIMIT $1",
                            max_partners,
                            default=[],
                        )
                        missing_partner_query = await _timed_query(
                            conn.fetchval,
                            "/* billing_preflight:partners_missing */ "
                            "SELECT COUNT(*) FROM storage_json WHERE partner_id IS NULL OR btrim(partner_id) = ''",
                            default=0,
                        )
                        if partner_id:
                            partner_present_query = await _timed_query(
                                conn.fetchval,
                                "/* billing_preflight:partner_present */ "
                                "SELECT 1 FROM storage_json WHERE partner_id=$1 LIMIT 1",
                                partner_id,
                                default=None,
                            )
                    except Exception as exc:
                        tenants_error_meta = _describe_exception(exc)
                        partners_found_query = _TimedQuery(
                            value=0, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None, error=tenants_error_meta
                        )
                        partners_sample_query = _TimedQuery(
                            value=[], status=STATUS_DEGRADED, latency_ms=None, lat_ms=None, error=tenants_error_meta
                        )
                        partners_top_query = _TimedQuery(
                            value=[], status=STATUS_DEGRADED, latency_ms=None, lat_ms=None, error=tenants_error_meta
                        )
                        missing_partner_query = _TimedQuery(
                            value=0, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None, error=tenants_error_meta
                        )
                        partner_present_query = _TimedQuery(
                            value=None, status=STATUS_DEGRADED, latency_ms=None, lat_ms=None, error=tenants_error_meta
                        )

                    payload_query = await _timed_query(
                        fetch_column_type,
                        conn,
                        "storage_json",
                        "payload",
                        default="unknown",
                    )
                    payload_type = payload_query.value or "unknown"

                    try:
                        total_balance_records, total_balance_meta = await _timed_aggregate(
                            count_payload_entries, conn, balances_file, column_type=payload_type, key="balances_total"
                        )
                        partners_with_balances, partners_with_balances_meta = await _timed_aggregate(
                            count_payload_nonempty,
                            conn,
                            balances_file,
                            column_type=payload_type,
                            key="balances_partners",
                        )
                        balances_updated_24h, balances_updated_meta = await _timed_aggregate(
                            run_scalar,
                            conn,
                            "balances_updated_24h",
                            "/* billing_preflight:balances_updated_24h */ "
                            "SELECT COUNT(*) FROM storage_json "
                            "WHERE filename=$1 AND updated_at >= now() - interval '24 hours'",
                            balances_file,
                        )
                        negative_balances, negative_balances_meta = await _timed_aggregate(
                            run_scalar,
                            conn,
                            "balances_negative",
                            "/* billing_preflight:balances_negative */ "
                            "SELECT COALESCE(SUM(CASE "
                            "WHEN value ~ '^-?\\d+(\\.\\d+)?$' AND value::numeric < 0 THEN 1 ELSE 0 END),0) "
                            "FROM storage_json s, jsonb_each_text(s.payload::jsonb) "
                            "WHERE s.filename=$1",
                            balances_file,
                        )
                    except Exception as exc:
                        total_balance_records = _aggregate_error_result(exc)
                        partners_with_balances = _aggregate_error_result(exc)
                        balances_updated_24h = _aggregate_error_result(exc)
                        negative_balances = _aggregate_error_result(exc)
                        total_balance_meta = _error_query_meta(exc)
                        partners_with_balances_meta = _error_query_meta(exc)
                        balances_updated_meta = _error_query_meta(exc)
                        negative_balances_meta = _error_query_meta(exc)

                    try:
                        total_user_records, total_user_meta = await _timed_aggregate(
                            count_payload_entries, conn, languages_file, column_type=payload_type, key="users_total"
                        )
                    except Exception as exc:
                        total_user_records = _aggregate_error_result(exc)
                        total_user_meta = _error_query_meta(exc)

                    try:
                        total_free_records, total_free_meta = await _timed_aggregate(
                            count_payload_entries, conn, free_file, column_type=payload_type, key="free_total"
                        )
                        partners_with_free, partners_with_free_meta = await _timed_aggregate(
                            count_payload_nonempty, conn, free_file, column_type=payload_type, key="free_partners"
                        )
                        free_range, free_range_meta = await _timed_aggregate(
                            run_row,
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
                        free_violations, free_violations_meta = await _timed_aggregate(
                            run_scalar,
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
                    except Exception as exc:
                        total_free_records = _aggregate_error_result(exc)
                        partners_with_free = _aggregate_error_result(exc)
                        free_range = _aggregate_error_result(exc)
                        free_violations = _aggregate_error_result(exc)
                        total_free_meta = _error_query_meta(exc)
                        partners_with_free_meta = _error_query_meta(exc)
                        free_range_meta = _error_query_meta(exc)
                        free_violations_meta = _error_query_meta(exc)

                    try:
                        total_attempts, total_attempts_meta = await _timed_aggregate(
                            count_payload_entries,
                            conn,
                            payments_file,
                            column_type=payload_type,
                            key="attempts_total",
                        )
                        attempts_last_24h, attempts_last_24h_meta = await _timed_aggregate(
                            run_scalar,
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
                        request_id_rows, request_id_rows_meta = await _timed_aggregate(
                            run_scalar,
                            conn,
                            "request_id_present",
                            "/* billing_preflight:request_id_present */ "
                            "SELECT COUNT(*) FROM storage_json s, jsonb_each(s.payload::jsonb) AS e(key, value) "
                            "WHERE s.filename=$1 AND value ? 'request_id'",
                            payments_file,
                        )
                        duplicate_request_id = AggregateResult(value=0, status=SQL_STATUS_OK, note="")
                        duplicate_request_id_meta = {
                            "status": STATUS_OK,
                            "latency_ms": 0,
                            "lat_ms": 0,
                        }
                        if request_id_rows.status == SQL_STATUS_OK and request_id_rows.value:
                            duplicate_request_id, duplicate_request_id_meta = await _timed_aggregate(
                                run_scalar,
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

                        stale_pending, stale_pending_meta = await _timed_aggregate(
                            run_scalar,
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
                    except Exception as exc:
                        total_attempts = _aggregate_error_result(exc)
                        attempts_last_24h = _aggregate_error_result(exc)
                        request_id_rows = _aggregate_error_result(exc)
                        duplicate_request_id = _aggregate_error_result(exc)
                        stale_pending = _aggregate_error_result(exc)
                        total_attempts_meta = _error_query_meta(exc)
                        attempts_last_24h_meta = _error_query_meta(exc)
                        request_id_rows_meta = _error_query_meta(exc)
                        duplicate_request_id_meta = _error_query_meta(exc)
                        stale_pending_meta = _error_query_meta(exc)
                break
            except Exception as exc:
                error_meta = _describe_exception(exc)
                logger.warning(
                    "BILLING_PREFLIGHT stats_read_retry attempt=%s/%s error_type=%s sqlstate=%s timeout=%s error=%s",
                    attempt,
                    query_retries,
                    error_meta.get("error_type"),
                    error_meta.get("sqlstate"),
                    error_meta.get("timeout", False),
                    error_meta.get("error"),
                )
                if attempt < query_retries:
                    await asyncio.sleep(query_backoff_s * attempt)
                else:
                    raise

        db_query_meta = _summarize_queries([("db_ping", db_ping.__dict__)])
        db_section = _Section(
            STATUS_OK if db_ping.status == STATUS_OK else STATUS_DEGRADED,
            "ok" if db_ping.status == STATUS_OK else "ping degraded",
            {"latency_ms": db_ping.latency_ms, "lat_ms": db_ping.lat_ms, **db_query_meta},
        )

        partners_found = partners_found_query.value or 0
        partner_rows = partners_sample_query.value or []
        partners_sample = [_hash_sample(row["partner_id"]) for row in partner_rows if row.get("partner_id")]
        top_rows = partners_top_query.value or []
        partners_top = [
            {"partner": _hash_sample(row["partner_id"]), "file_count": int(row["file_count"])}
            for row in top_rows
            if row.get("partner_id")
        ]
        missing_partner_rows = missing_partner_query.value or 0
        partner_present = partner_present_query.value if partner_id else None

        tenants_status = STATUS_OK
        tenants_details = f"found={int(partners_found)}, sample={partners_sample}"
        tenant_meta = {
            "partners_found": int(partners_found),
            "partners_sample": partners_sample,
            "partners_top": partners_top[: min(3, len(partners_top))],
            "storage_partner": _mask_partner_id(partner_id),
        }
        tenant_queries = _summarize_queries(
            [
                ("partners_count", partners_found_query.__dict__),
                ("partners_sample", partners_sample_query.__dict__),
                ("partners_top", partners_top_query.__dict__),
                ("partners_missing", missing_partner_query.__dict__),
            ]
        )
        if partner_id:
            tenant_queries = _summarize_queries(
                [
                    ("partners_count", partners_found_query.__dict__),
                    ("partners_sample", partners_sample_query.__dict__),
                    ("partners_top", partners_top_query.__dict__),
                    ("partners_missing", missing_partner_query.__dict__),
                    ("partner_present", partner_present_query.__dict__),
                ]
            )
        tenant_meta.update(tenant_queries)
        if tenant_meta.get("query_status") == STATUS_DEGRADED:
            tenants_status = STATUS_DEGRADED
            tenants_details = _append_error_details("query degraded", tenant_meta)
        elif missing_partner_rows:
            tenants_status = STATUS_DEGRADED
            tenants_details = f"missing_partner_id={int(missing_partner_rows)}"
        elif partner_id and not partner_present and partners_found:
            tenants_status = STATUS_DEGRADED
            tenants_details = "tenant isolation mismatch"

        balances_meta_summary = _summarize_queries(
            [
                ("column_type", payload_query.__dict__),
                ("balances_total", total_balance_meta),
                ("balances_partners", partners_with_balances_meta),
                ("balances_updated_24h", balances_updated_meta),
                ("balances_negative", negative_balances_meta),
            ]
        )
        users_meta_summary = _summarize_queries(
            [
                ("column_type", payload_query.__dict__),
                ("users_total", total_user_meta),
            ]
        )
        free_meta_summary = _summarize_queries(
            [
                ("column_type", payload_query.__dict__),
                ("free_total", total_free_meta),
                ("free_partners", partners_with_free_meta),
                ("free_range", free_range_meta),
                ("free_violations", free_violations_meta),
            ]
        )
        attempts_meta_summary = _summarize_queries(
            [
                ("column_type", payload_query.__dict__),
                ("attempts_total", total_attempts_meta),
                ("attempts_last_24h", attempts_last_24h_meta),
                ("request_id_present", request_id_rows_meta),
                ("request_id_duplicates", duplicate_request_id_meta),
                ("stale_pending", stale_pending_meta),
            ]
        )

        balances_status = STATUS_OK
        balances_note = ""
        balances_details = (
            f"records={total_balance_records.value if total_balance_records.value is not None else 'n/a'}, "
            f"partners={partners_with_balances.value if partners_with_balances.value is not None else 'n/a'}, "
            f"neg={negative_balances.value if negative_balances.value is not None else 'n/a'}, "
            f"updated24h={balances_updated_24h.value if balances_updated_24h.value is not None else 'n/a'}"
        )
        balances_merge = merge_status(
            total_balance_records,
            partners_with_balances,
            balances_updated_24h,
            negative_balances,
        )
        if balances_merge in {STATUS_ERROR, SQL_STATUS_UNKNOWN}:
            balances_status = STATUS_UNKNOWN
            balances_note = f" ({total_balance_records.note or 'aggregate_compat'})"
        if total_balance_records.value == 0:
            balances_details += " (initialized=0)"
        if negative_balances.status == SQL_STATUS_OK and negative_balances.value:
            balances_status = STATUS_DEGRADED if balances_status != STATUS_UNKNOWN else balances_status
            balances_note = " (negative balances)"
        if balances_meta_summary.get("query_status") == STATUS_DEGRADED:
            balances_status = STATUS_DEGRADED
            balances_details = _append_error_details(balances_details, balances_meta_summary)

        users_status = STATUS_OK
        users_note = ""
        if total_user_records.status != SQL_STATUS_OK:
            users_status = STATUS_UNKNOWN
            users_note = f" ({total_user_records.note or 'aggregate_compat'})"
        users_details = f"records={total_user_records.value if total_user_records.value is not None else 'n/a'}"
        if total_user_records.value == 0:
            users_details += " (initialized=0)"
        if users_meta_summary.get("query_status") == STATUS_DEGRADED:
            users_status = STATUS_DEGRADED
            users_details = _append_error_details(users_details, users_meta_summary)

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
        if free_meta_summary.get("query_status") == STATUS_DEGRADED:
            free_status = STATUS_DEGRADED
            free_details = _append_error_details(free_details, free_meta_summary)

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
        if attempts_meta_summary.get("query_status") == STATUS_DEGRADED:
            attempts_status = STATUS_DEGRADED
            attempts_details = _append_error_details(attempts_details, attempts_meta_summary)

        storage_rw_section = await _storage_rw_smoke(storage, pool, bot_instance_id=partner_id)

        report["sections"] = {
            "db": {"status": db_section.status, "details": db_section.details, "meta": db_section.meta},
            "tenants": {"status": tenants_status, "details": tenants_details, "meta": tenant_meta},
            "users": {
                "status": users_status,
                "details": users_details,
                "meta": {"records": total_user_records.value, "note": users_note, **users_meta_summary},
            },
            "balances": {
                "status": balances_status,
                "details": balances_details,
                "meta": {"records": total_balance_records.value, "note": balances_note, **balances_meta_summary},
            },
            "free_limits": {
                "status": free_status,
                "details": free_details,
                "meta": {
                    "daily_limit": free_limit,
                    "records": total_free_records.value,
                    "note": free_note,
                    **free_meta_summary,
                },
            },
            "attempts": {
                "status": attempts_status,
                "details": attempts_details,
                "meta": {
                    "stale_minutes": stale_minutes,
                    "total": total_attempts.value,
                    "last24h": attempts_last_24h.value,
                    "dup_request_id": duplicate_request_id.value,
                    "note": attempts_note,
                    **attempts_meta_summary,
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
                _Section(users_status, users_details, {}),
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
