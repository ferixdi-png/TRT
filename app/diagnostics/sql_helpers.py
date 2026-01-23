from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_UNKNOWN = "unknown"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class AggregateResult:
    value: Any
    status: str
    note: str = ""


def _normalize_column_type(data_type: Optional[str], udt_name: Optional[str]) -> str:
    normalized = (udt_name or data_type or "").lower()
    if "jsonb" in normalized:
        return "jsonb"
    if normalized == "json":
        return "json"
    if normalized in {"text", "varchar", "character varying", "character", "char"}:
        return "text"
    return "unknown"


async def fetch_column_type(conn, table: str, column: str) -> str:
    try:
        row = await conn.fetchrow(
            "/* billing_preflight:column_type */ "
            "SELECT data_type, udt_name "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=$1 AND column_name=$2",
            table,
            column,
        )
    except Exception as exc:
        logger.debug("billing_preflight: column type lookup failed: %s", exc, exc_info=True)
        return "unknown"
    if not row:
        return "unknown"
    return _normalize_column_type(row.get("data_type"), row.get("udt_name"))


async def run_scalar(conn, key: str, sql: str, *args: Any) -> AggregateResult:
    try:
        value = await conn.fetchval(sql, *args)
        return AggregateResult(value=value, status=STATUS_OK, note="")
    except Exception as exc:
        logger.debug("billing_preflight: %s failed: %s", key, exc, exc_info=True)
        return AggregateResult(value=None, status=STATUS_ERROR, note=str(exc)[:120])


async def run_row(conn, key: str, sql: str, *args: Any) -> AggregateResult:
    try:
        value = await conn.fetchrow(sql, *args)
        return AggregateResult(value=value, status=STATUS_OK, note="")
    except Exception as exc:
        logger.debug("billing_preflight: %s failed: %s", key, exc, exc_info=True)
        return AggregateResult(value=None, status=STATUS_ERROR, note=str(exc)[:120])


def _count_entries_sql(column_expr: str, key: str, *, json_typeof: str, json_each: str, json_array_len: str) -> str:
    return (
        f"/* billing_preflight:{key} */ "
        "SELECT COALESCE(SUM(CASE "
        f"WHEN {json_typeof}({column_expr}) = 'object' THEN "
        f"(SELECT COUNT(*) FROM {json_each}({column_expr})) "
        f"WHEN {json_typeof}({column_expr}) = 'array' THEN {json_array_len}({column_expr}) "
        "ELSE 0 END),0) "
        f"FROM storage_json WHERE filename=$1"
    )


def _count_nonempty_sql(column_expr: str, key: str, *, json_typeof: str, json_each: str, json_array_len: str) -> str:
    return (
        f"/* billing_preflight:{key} */ "
        "SELECT COUNT(*) FROM storage_json WHERE filename=$1 AND ("
        f"CASE WHEN {json_typeof}({column_expr}) = 'object' THEN "
        f"(SELECT COUNT(*) FROM {json_each}({column_expr})) "
        f"WHEN {json_typeof}({column_expr}) = 'array' THEN {json_array_len}({column_expr}) "
        "ELSE 0 END"
        ") > 0"
    )


async def count_payload_entries(conn, filename: str, *, column_type: str, key: str) -> AggregateResult:
    if column_type == "unknown":
        fallback = await run_scalar(
            conn,
            f"{key}_fallback",
            f"/* billing_preflight:{key}_fallback */ SELECT COUNT(*) FROM storage_json WHERE filename=$1",
            filename,
        )
        if fallback.status == STATUS_OK:
            return AggregateResult(value=fallback.value, status=STATUS_UNKNOWN, note="fallback=count_rows")
        return AggregateResult(value=None, status=STATUS_ERROR, note=fallback.note)

    if column_type == "jsonb":
        column_expr = "payload::jsonb"
        json_typeof = "jsonb_typeof"
        json_each = "jsonb_each"
        json_array_len = "jsonb_array_length"
    else:
        column_expr = "payload::json"
        if column_type == "text":
            column_expr = "NULLIF(payload, '')::json"
        json_typeof = "json_typeof"
        json_each = "json_each"
        json_array_len = "json_array_length"
    sql = _count_entries_sql(
        column_expr,
        key,
        json_typeof=json_typeof,
        json_each=json_each,
        json_array_len=json_array_len,
    )
    result = await run_scalar(conn, key, sql, filename)
    if result.status == STATUS_OK:
        return result
    fallback = await run_scalar(
        conn,
        f"{key}_fallback",
        f"/* billing_preflight:{key}_fallback */ SELECT COUNT(*) FROM storage_json WHERE filename=$1",
        filename,
    )
    if fallback.status == STATUS_OK:
        note = "fallback=count_rows"
        return AggregateResult(value=fallback.value, status=STATUS_UNKNOWN, note=note)
    return AggregateResult(value=None, status=STATUS_ERROR, note=result.note)


async def count_payload_nonempty(conn, filename: str, *, column_type: str, key: str) -> AggregateResult:
    if column_type == "unknown":
        fallback = await run_scalar(
            conn,
            f"{key}_fallback",
            f"/* billing_preflight:{key}_fallback */ SELECT COUNT(*) FROM storage_json WHERE filename=$1",
            filename,
        )
        if fallback.status == STATUS_OK:
            return AggregateResult(value=fallback.value, status=STATUS_UNKNOWN, note="fallback=count_rows")
        return AggregateResult(value=None, status=STATUS_ERROR, note=fallback.note)

    if column_type == "jsonb":
        column_expr = "payload::jsonb"
        json_typeof = "jsonb_typeof"
        json_each = "jsonb_each"
        json_array_len = "jsonb_array_length"
    else:
        column_expr = "payload::json"
        if column_type == "text":
            column_expr = "NULLIF(payload, '')::json"
        json_typeof = "json_typeof"
        json_each = "json_each"
        json_array_len = "json_array_length"
    sql = _count_nonempty_sql(
        column_expr,
        key,
        json_typeof=json_typeof,
        json_each=json_each,
        json_array_len=json_array_len,
    )
    result = await run_scalar(conn, key, sql, filename)
    if result.status == STATUS_OK:
        return result
    fallback = await run_scalar(
        conn,
        f"{key}_fallback",
        f"/* billing_preflight:{key}_fallback */ SELECT COUNT(*) FROM storage_json WHERE filename=$1",
        filename,
    )
    if fallback.status == STATUS_OK:
        note = "fallback=count_rows"
        return AggregateResult(value=fallback.value, status=STATUS_UNKNOWN, note=note)
    return AggregateResult(value=None, status=STATUS_ERROR, note=result.note)


def merge_status(*results: AggregateResult) -> str:
    statuses = {result.status for result in results}
    if STATUS_ERROR in statuses:
        return STATUS_ERROR
    if STATUS_UNKNOWN in statuses:
        return STATUS_UNKNOWN
    return STATUS_OK
