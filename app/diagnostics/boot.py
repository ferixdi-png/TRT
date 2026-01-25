from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import time
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import asyncpg

from app.config_env import is_valid_instance_slug, normalize_webhook_base_url
from app.storage import get_storage

logger = logging.getLogger(__name__)

STATUS_OK = "OK"
STATUS_DEGRADED = "DEGRADED"
STATUS_FAIL = "FAIL"

RESULT_READY = "READY"
RESULT_DEGRADED = "DEGRADED"
RESULT_FAIL = "FAIL"

_ALLOWED_BOT_MODES = {"polling", "webhook", "web", "worker", "bot", "auto", "smoke"}
_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")

_BOOT_REPORT_KEY = "_diagnostics/boot.json"

_cached_boot_report: Optional[Dict[str, Any]] = None
_cached_boot_report_text: Optional[str] = None


def _env_value(config: Any, name: str, default: str = "") -> str:
    if hasattr(config, "get"):
        return str(config.get(name, default) or "").strip()
    return str(getattr(config, name, default) or "").strip()


def _status_entry(
    status: str,
    *,
    details: str = "",
    hint: str = "",
    latency_ms: Optional[float] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"status": status}
    if latency_ms is not None:
        entry["latency_ms"] = round(latency_ms, 2)
    if details:
        entry["details"] = details
    if hint:
        entry["hint"] = hint
    return entry


def _section_status(checks: Dict[str, Dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks.values() if check}
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_DEGRADED in statuses:
        return STATUS_DEGRADED
    return STATUS_OK


def _bool_env(config: Any, name: str) -> bool:
    return bool(_env_value(config, name))


def _is_https_url(value: str) -> bool:
    if not value:
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc)


def _is_valid_instance(value: str) -> bool:
    if not value:
        return False
    if " " in value:
        return False
    return is_valid_instance_slug(value)


def _safe_set_status(value: str) -> str:
    return "SET" if value else "NOT_SET"


def _build_how_to_fix(critical_failures: Dict[str, str]) -> list[str]:
    hints = []
    for key, hint in critical_failures.items():
        hints.append(f"{key}: {hint}")
    return hints


def _format_latency(detail: Dict[str, Any]) -> str:
    if "latency_ms" in detail:
        return f" latency={detail['latency_ms']}ms"
    return ""


def _format_section_line(section: str, detail: Dict[str, Any]) -> str:
    latency = _format_latency(detail)
    details = detail.get("details")
    suffix = f" ({details})" if details else ""
    return f"{section}: {detail['status']}{latency}{suffix}"


def format_boot_report(report: Dict[str, Any]) -> str:
    header = (
        "BOOT DIAGNOSTICS "
        f"(bot_instance_id={report['meta'].get('bot_instance_id', 'n/a')}, "
        f"mode={report['meta'].get('bot_mode', 'n/a')}, "
        f"port={report['meta'].get('port', 'n/a')})"
    )
    lines = [header]

    summary = report.get("summary", {})
    for key in [
        "CONFIG",
        "NETWORK/PORT",
        "DATABASE",
        "STORAGE",
        "REDIS",
        "TELEGRAM",
        "WEBHOOK",
        "AI",
        "UX",
        "DATA_INTEGRITY",
    ]:
        detail = summary.get(key)
        if detail:
            lines.append(_format_section_line(key, detail))
    lines.append(f"RESULT: {report['result']}")

    how_to_fix = report.get("how_to_fix") or []
    if how_to_fix:
        lines.append("HOW TO FIX:")
        for item in how_to_fix:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _cache_boot_report(report: Dict[str, Any], human: str) -> None:
    global _cached_boot_report, _cached_boot_report_text
    _cached_boot_report = report
    _cached_boot_report_text = human


def get_cached_boot_report() -> Optional[Dict[str, Any]]:
    return _cached_boot_report


def get_cached_boot_report_text() -> Optional[str]:
    return _cached_boot_report_text


def _build_report_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, default=str)


def log_boot_report(report: Dict[str, Any]) -> None:
    human = format_boot_report(report)
    logger.info("BOOT_REPORT %s", _build_report_json(report))
    logger.info("%s", human)
    _cache_boot_report(report, human)


def _record_summary(section_name: str, section: Dict[str, Any], summary: Dict[str, Any]) -> None:
    summary[section_name] = {
        "status": section["status"],
        **{k: v for k, v in section.get("meta", {}).items() if k in {"details", "latency_ms"}},
    }


async def _check_port_bind(port: int) -> Dict[str, Any]:
    if not (1 <= port <= 65535):
        return _status_entry(STATUS_FAIL, details=f"invalid port {port}", hint="Set PORT to 1-65535")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.close()
        return _status_entry(STATUS_OK, details=f"bind ok 0.0.0.0:{port}")
    except OSError as exc:
        return _status_entry(
            STATUS_FAIL,
            details=f"bind failed 0.0.0.0:{port}",
            hint=f"Ensure port is свободен и доступен (error: {exc})",
        )


async def _check_db_connect(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return _status_entry(STATUS_FAIL, details="DATABASE_URL missing", hint="Set DATABASE_URL")
    start = time.perf_counter()
    try:
        conn = await asyncpg.connect(database_url)
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="connect failed", hint=str(exc)[:120])
    latency = (time.perf_counter() - start) * 1000
    await conn.close()
    return _status_entry(STATUS_OK, details="connected", latency_ms=latency)


async def _check_db_query(database_url: str) -> Dict[str, Any]:
    if not database_url:
        return _status_entry(STATUS_FAIL, details="DATABASE_URL missing", hint="Set DATABASE_URL")
    start = time.perf_counter()
    try:
        conn = await asyncpg.connect(database_url)
        value = await conn.fetchval("SELECT 1")
        await conn.close()
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="SELECT 1 failed", hint=str(exc)[:120])
    latency = (time.perf_counter() - start) * 1000
    if value != 1:
        return _status_entry(STATUS_FAIL, details="SELECT 1 returned unexpected", hint="Check DB connectivity")
    return _status_entry(STATUS_OK, details="SELECT 1 ok", latency_ms=latency)


async def _storage_rw_smoke(storage: Any) -> Dict[str, Any]:
    if storage is None:
        return _status_entry(STATUS_FAIL, details="storage unavailable", hint="Fix DATABASE_URL/BOT_INSTANCE_ID")
    payload = {"ts": datetime.utcnow().isoformat(), "ok": True}
    try:
        await storage.write_json_file(_BOOT_REPORT_KEY, payload)
        loaded = await storage.read_json_file(_BOOT_REPORT_KEY, default={})
        if loaded.get("ok") is not True:
            return _status_entry(STATUS_FAIL, details="rw mismatch", hint="Check DB storage JSON table")
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="rw failed", hint=str(exc)[:120])
    return _status_entry(STATUS_OK, details="rw ok")


async def _check_data_integrity(storage: Any) -> Dict[str, Any]:
    if storage is None:
        return _status_entry(STATUS_FAIL, details="storage unavailable", hint="Fix DATABASE_URL/BOT_INSTANCE_ID")
    files = ["user_registry.json", "payments.json", "referrals.json", "generations_history.json"]
    initialized = []
    for filename in files:
        try:
            payload = await storage.read_json_file(filename, default={})
            if payload == {}:
                await storage.write_json_file(filename, payload)
                initialized.append(filename)
        except Exception as exc:
            return _status_entry(STATUS_DEGRADED, details=f"{filename} error", hint=str(exc)[:120])
    details = "initialized: " + ", ".join(initialized) if initialized else "ok"
    return _status_entry(STATUS_OK, details=details)


async def _check_redis(redis_url: str, redis_client: Any = None) -> Dict[str, Any]:
    if not redis_url:
        return _status_entry(STATUS_DEGRADED, details="not configured", hint="Set REDIS_URL to enable")
    try:
        if redis_client is None:
            import redis.asyncio as redis  # type: ignore

            redis_client = redis.from_url(redis_url, decode_responses=True)
        start = time.perf_counter()
        await redis_client.ping()
        latency = (time.perf_counter() - start) * 1000
        if hasattr(redis_client, "close"):
            await redis_client.close()
        return _status_entry(STATUS_OK, details="ping ok", latency_ms=latency)
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="ping failed", hint=str(exc)[:120])


def _check_handlers() -> Dict[str, Any]:
    try:
        import bot_kie
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="bot_kie import failed", hint=str(exc)[:120])
    missing = [
        name
        for name in ["start", "button_callback", "ensure_main_menu"]
        if not hasattr(bot_kie, name)
    ]
    try:
        from app.admin import router as admin_router

        if not hasattr(admin_router, "show_admin_root") or not hasattr(admin_router, "admin_callback"):
            missing.append("admin_router")
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="admin router import failed", hint=str(exc)[:120])
    if missing:
        return _status_entry(STATUS_FAIL, details=f"missing: {', '.join(missing)}", hint="Ensure handlers are defined")
    return _status_entry(STATUS_OK, details="handlers registered")


def _check_unknown_callback_fallback() -> Dict[str, Any]:
    try:
        from app.buttons.fallback import fallback_callback_handler
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="fallback import failed", hint=str(exc)[:120])
    if not callable(fallback_callback_handler):
        return _status_entry(STATUS_FAIL, details="fallback handler missing", hint="Ensure fallback exists")
    return _status_entry(STATUS_OK, details="fallback ok")


def _check_no_silence_guard() -> Dict[str, Any]:
    try:
        from app.observability.no_silence_guard import get_no_silence_guard

        guard = get_no_silence_guard()
    except Exception as exc:
        return _status_entry(STATUS_DEGRADED, details="guard unavailable", hint=str(exc)[:120])
    if not hasattr(guard, "check_and_ensure_response"):
        return _status_entry(STATUS_DEGRADED, details="guard missing methods", hint="Update no_silence_guard")
    return _status_entry(STATUS_OK, details="guard ok")


def _check_webhook_handler() -> Dict[str, Any]:
    try:
        import bot_kie
    except Exception as exc:
        return _status_entry(STATUS_FAIL, details="bot_kie import failed", hint=str(exc)[:120])
    handler = getattr(bot_kie, "create_webhook_handler", None)
    if handler is None:
        return _status_entry(STATUS_DEGRADED, details="create_webhook_handler missing")
    if not callable(handler):
        return _status_entry(STATUS_FAIL, details="create_webhook_handler not callable")
    return _status_entry(STATUS_OK, details="handler available")


async def _persist_boot_report(storage: Any, report: Dict[str, Any]) -> None:
    if storage is None:
        return
    try:
        await storage.write_json_file(_BOOT_REPORT_KEY, report)
    except Exception as exc:
        logger.warning("BOOT_REPORT persist failed: %s", exc)


async def run_boot_diagnostics(config: Any, storage: Any, redis_client: Any = None) -> Dict[str, Any]:
    diagnostics_started = datetime.utcnow().isoformat()
    summary: Dict[str, Any] = {}
    critical_failures: Dict[str, str] = {}
    degraded_notes: Dict[str, str] = {}

    admin_id = _env_value(config, "ADMIN_ID")
    bot_instance_id = _env_value(config, "BOT_INSTANCE_ID")
    bot_mode_raw = _env_value(config, "BOT_MODE")
    bot_mode = bot_mode_raw or "auto"
    webhook_base_raw = _env_value(config, "WEBHOOK_BASE_URL")
    webhook_base = normalize_webhook_base_url(webhook_base_raw)
    port_value = _env_value(config, "PORT") or "10000"
    database_url = _env_value(config, "DATABASE_URL")
    telegram_token = _env_value(config, "TELEGRAM_BOT_TOKEN")
    redis_url = _env_value(config, "REDIS_URL")
    kie_api_key = _env_value(config, "KIE_API_KEY")

    webhook_required = bot_mode_raw in {"webhook", "web"}

    config_checks: Dict[str, Dict[str, Any]] = {}
    if not admin_id:
        config_checks["ADMIN_ID"] = _status_entry(STATUS_FAIL, details="missing", hint="Set ADMIN_ID")
        critical_failures["ADMIN_ID"] = "Set ADMIN_ID to numeric Telegram user id(s)"
    else:
        admin_parts = [p for p in re.split(r"[,\s]+", admin_id.strip()) if p]
        if not admin_parts or any(not part.isdigit() for part in admin_parts):
            config_checks["ADMIN_ID"] = _status_entry(STATUS_FAIL, details="not numeric", hint="ADMIN_ID must be int list")
            critical_failures["ADMIN_ID"] = "Set ADMIN_ID to numeric Telegram user id(s)"
        else:
            config_checks["ADMIN_ID"] = _status_entry(STATUS_OK, details="valid")

    normalized_instance = bot_instance_id.lower()
    if not bot_instance_id:
        config_checks["BOT_INSTANCE_ID"] = _status_entry(STATUS_FAIL, details="missing", hint="Set BOT_INSTANCE_ID")
        critical_failures["BOT_INSTANCE_ID"] = "Set BOT_INSTANCE_ID to lowercase identifier"
    elif not _is_valid_instance(bot_instance_id):
        config_checks["BOT_INSTANCE_ID"] = _status_entry(
            STATUS_FAIL,
            details="invalid format",
            hint="Use lowercase letters, digits, . _ - (slug)",
        )
        critical_failures["BOT_INSTANCE_ID"] = "Use lowercase letters, digits, . _ - (3-32 chars)"
    else:
        config_checks["BOT_INSTANCE_ID"] = _status_entry(STATUS_OK, details=f"normalized={normalized_instance}")

    if not bot_mode_raw:
        config_checks["BOT_MODE"] = _status_entry(STATUS_DEGRADED, details=f"default={bot_mode}")
        degraded_notes["BOT_MODE"] = "BOT_MODE not set; default applied"
    elif bot_mode_raw not in _ALLOWED_BOT_MODES:
        config_checks["BOT_MODE"] = _status_entry(
            STATUS_DEGRADED,
            details="unknown mode",
            hint="Use polling/webhook/web/worker/bot/auto",
        )
    else:
        config_checks["BOT_MODE"] = _status_entry(STATUS_OK, details=bot_mode_raw)

    if not webhook_base_raw:
        config_checks["WEBHOOK_BASE_URL"] = _status_entry(STATUS_FAIL, details="missing", hint="Set WEBHOOK_BASE_URL")
        if webhook_required:
            critical_failures["WEBHOOK_BASE_URL"] = "Set https WEBHOOK_BASE_URL for webhook mode"
    elif not _is_https_url(webhook_base_raw):
        config_checks["WEBHOOK_BASE_URL"] = _status_entry(
            STATUS_FAIL,
            details="not https",
            hint="Use https:// URL",
        )
        if webhook_required:
            critical_failures["WEBHOOK_BASE_URL"] = "Set https WEBHOOK_BASE_URL for webhook mode"
    else:
        normalized_note = "normalized" if webhook_base != webhook_base_raw else "ok"
        config_checks["WEBHOOK_BASE_URL"] = _status_entry(STATUS_OK, details=normalized_note)

    try:
        port = int(port_value)
        config_checks["PORT"] = _status_entry(STATUS_OK, details=str(port))
    except ValueError:
        port = 10000
        config_checks["PORT"] = _status_entry(STATUS_FAIL, details="invalid", hint="Set PORT to int")
        critical_failures["PORT"] = "Set PORT to valid integer"

    config_checks["STORAGE_MODE"] = _status_entry(STATUS_OK, details="db-only")

    config_checks["KIE_API_KEY"] = _status_entry(
        STATUS_OK if kie_api_key else STATUS_DEGRADED,
        details=_safe_set_status(kie_api_key),
        hint="AI disabled" if not kie_api_key else "",
    )
    if not kie_api_key:
        degraded_notes["KIE_API_KEY"] = "AI generation disabled"

    payment_support_set = any(
        _bool_env(config, name)
        for name in [
            "PAYMENT_BANK",
            "PAYMENT_CARD_HOLDER",
            "PAYMENT_PHONE",
            "SUPPORT_TELEGRAM",
            "SUPPORT_TEXT",
        ]
    )
    config_checks["PAYMENT_SUPPORT"] = _status_entry(
        STATUS_OK if payment_support_set else STATUS_DEGRADED,
        details="SET" if payment_support_set else "owner defaults",
        hint="Set PAYMENT_/SUPPORT_ vars" if not payment_support_set else "",
    )
    if not payment_support_set:
        degraded_notes["PAYMENT_SUPPORT"] = "Owner defaults in use"

    config_section = {
        "status": _section_status(config_checks),
        "checks": config_checks,
    }
    _record_summary("CONFIG", config_section, summary)

    network_checks = {
        "healthcheck_bind": await _check_port_bind(port),
    }
    network_section = {
        "status": _section_status(network_checks),
        "checks": network_checks,
        "meta": network_checks.get("healthcheck_bind", {}),
    }
    if network_checks["healthcheck_bind"]["status"] == STATUS_FAIL:
        critical_failures["PORT_BIND"] = "Ensure PORT is available and not used by another process"
    _record_summary("NETWORK/PORT", network_section, summary)

    db_connect = await _check_db_connect(database_url)
    db_query = await _check_db_query(database_url)
    db_maxconn_raw = _env_value(config, "DB_MAX_CONN", "5")
    try:
        db_maxconn = int(db_maxconn_raw)
    except ValueError:
        db_maxconn = 5
    pool_status = STATUS_OK if db_maxconn >= 2 else STATUS_DEGRADED
    db_checks = {
        "connect": db_connect,
        "query": db_query,
        "pool_size": _status_entry(
            pool_status,
            details=str(db_maxconn),
            hint="Consider DB_MAX_CONN>=2" if pool_status == STATUS_DEGRADED else "",
        ),
    }
    db_section = {
        "status": _section_status(db_checks),
        "checks": db_checks,
        "meta": db_query if db_query["status"] == STATUS_OK else db_connect,
    }
    if db_connect["status"] == STATUS_FAIL or db_query["status"] == STATUS_FAIL:
        critical_failures["DATABASE"] = "Verify DATABASE_URL and DB availability"
    _record_summary("DATABASE", db_section, summary)

    storage_instance = storage
    if storage_instance is None:
        try:
            storage_instance = get_storage()
        except Exception as exc:
            storage_instance = None
            degraded_notes["STORAGE_INIT"] = str(exc)[:120]
    storage_checks = {
        "backend": _status_entry(STATUS_OK, details="db-only"),
        "tenant_namespace": _status_entry(
            STATUS_OK if bot_instance_id else STATUS_FAIL,
            details=bot_instance_id or "missing",
            hint="Set BOT_INSTANCE_ID" if not bot_instance_id else "",
        ),
        "rw_smoke": await _storage_rw_smoke(storage_instance),
        "lock_concurrency": _status_entry(
            STATUS_OK if hasattr(storage_instance, "_get_file_lock") else STATUS_DEGRADED,
            details="locks ok" if hasattr(storage_instance, "_get_file_lock") else "locks unavailable",
        ),
    }
    storage_section = {
        "status": _section_status(storage_checks),
        "checks": storage_checks,
        "meta": storage_checks.get("rw_smoke", {}),
    }
    if storage_checks["rw_smoke"]["status"] == STATUS_FAIL:
        critical_failures["STORAGE"] = "Fix storage connectivity and DB schema"
    _record_summary("STORAGE", storage_section, summary)

    redis_checks = {"ping": await _check_redis(redis_url, redis_client=redis_client)}
    redis_section = {
        "status": _section_status(redis_checks),
        "checks": redis_checks,
        "meta": redis_checks.get("ping", {}),
    }
    if redis_checks["ping"]["status"] == STATUS_FAIL:
        degraded_notes["REDIS"] = "Redis ping failed"
    _record_summary("REDIS", redis_section, summary)

    telegram_checks: Dict[str, Dict[str, Any]] = {}
    if not telegram_token:
        telegram_checks["token_format"] = _status_entry(STATUS_FAIL, details="missing", hint="Set TELEGRAM_BOT_TOKEN")
        critical_failures["TELEGRAM_BOT_TOKEN"] = "Set TELEGRAM_BOT_TOKEN"
    elif not _TOKEN_RE.match(telegram_token):
        telegram_checks["token_format"] = _status_entry(STATUS_FAIL, details="invalid format")
        critical_failures["TELEGRAM_BOT_TOKEN"] = "Fix TELEGRAM_BOT_TOKEN format"
    else:
        telegram_checks["token_format"] = _status_entry(STATUS_OK, details="format ok")

    if webhook_required:
        webhook_status = STATUS_OK if _is_https_url(webhook_base_raw) else STATUS_FAIL
        telegram_checks["webhook_mode"] = _status_entry(
            webhook_status,
            details="required",
            hint="Set WEBHOOK_BASE_URL https" if webhook_status == STATUS_FAIL else "",
        )
        if webhook_status == STATUS_FAIL:
            critical_failures["WEBHOOK_BASE_URL"] = "Set https WEBHOOK_BASE_URL for webhook mode"
    else:
        telegram_checks["webhook_mode"] = _status_entry(STATUS_OK, details="polling/auto")

    run_getme = _env_value(config, "BOOT_DIAGNOSTICS_GETME") == "1"
    if run_getme and telegram_token:
        try:
            from telegram import Bot

            start = time.perf_counter()
            bot = Bot(token=telegram_token)
            me = await bot.get_me()
            latency = (time.perf_counter() - start) * 1000
            telegram_checks["getMe"] = _status_entry(
                STATUS_OK,
                details=f"@{me.username}" if me.username else "ok",
                latency_ms=latency,
            )
        except Exception as exc:
            telegram_checks["getMe"] = _status_entry(STATUS_DEGRADED, details="getMe failed", hint=str(exc)[:120])
    else:
        telegram_checks["getMe"] = _status_entry(STATUS_OK, details="skipped")

    telegram_section = {
        "status": _section_status(telegram_checks),
        "checks": telegram_checks,
        "meta": telegram_checks.get("getMe", telegram_checks.get("token_format", {})),
    }
    _record_summary("TELEGRAM", telegram_section, summary)

    webhook_checks: Dict[str, Dict[str, Any]] = {}
    if webhook_required:
        webhook_checks["base_url"] = _status_entry(
            STATUS_OK if _is_https_url(webhook_base_raw) else STATUS_FAIL,
            details="https" if _is_https_url(webhook_base_raw) else "invalid",
            hint="Set https WEBHOOK_BASE_URL" if not _is_https_url(webhook_base_raw) else "",
        )
        webhook_checks["handler"] = _check_webhook_handler()
    else:
        webhook_checks["base_url"] = _status_entry(STATUS_OK, details="polling/auto")
        webhook_checks["handler"] = _status_entry(STATUS_OK, details="not required")
    webhook_section = {
        "status": _section_status(webhook_checks),
        "checks": webhook_checks,
    }
    _record_summary("WEBHOOK", webhook_section, summary)

    ai_checks = {
        "KIE": _status_entry(
            STATUS_OK if kie_api_key else STATUS_DEGRADED,
            details=_safe_set_status(kie_api_key),
            hint="AI disabled" if not kie_api_key else "",
        )
    }
    ai_section = {
        "status": _section_status(ai_checks),
        "checks": ai_checks,
        "meta": ai_checks["KIE"],
    }
    _record_summary("AI", ai_section, summary)

    ux_checks = {
        "handlers": _check_handlers(),
        "unknown_callback": _check_unknown_callback_fallback(),
        "anti_double_click_guard": _check_no_silence_guard(),
    }
    ux_section = {
        "status": _section_status(ux_checks),
        "checks": ux_checks,
    }
    _record_summary("UX", ux_section, summary)

    data_integrity = await _check_data_integrity(storage_instance)
    data_section = {
        "status": data_integrity["status"],
        "checks": {"base_structures": data_integrity},
        "meta": data_integrity,
    }
    _record_summary("DATA_INTEGRITY", data_section, summary)

    result = RESULT_READY
    if critical_failures:
        result = RESULT_FAIL
    elif any(value["status"] in {STATUS_DEGRADED, STATUS_FAIL} for value in summary.values()):
        result = RESULT_DEGRADED

    report = {
        "timestamp": diagnostics_started,
        "result": result,
        "meta": {
            "bot_instance_id": bot_instance_id,
            "bot_mode": bot_mode,
            "port": port,
        },
        "sections": {
            "CONFIG": config_section,
            "NETWORK/PORT": network_section,
            "DATABASE": db_section,
            "STORAGE": storage_section,
            "REDIS": redis_section,
            "TELEGRAM": telegram_section,
            "WEBHOOK": webhook_section,
            "AI": ai_section,
            "UX": ux_section,
            "DATA_INTEGRITY": data_section,
        },
        "summary": summary,
        "critical_failures": critical_failures,
        "degraded_notes": degraded_notes,
        "how_to_fix": _build_how_to_fix(critical_failures),
    }

    await _persist_boot_report(storage_instance, report)
    human = format_boot_report(report)
    _cache_boot_report(report, human)
    return report
