from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

from app.config_env import normalize_webhook_base_url, validate_config
from app.diagnostics.db_health import check_db_health
from app.diagnostics.boot import format_boot_report, get_cached_boot_report, get_cached_boot_report_text
from app.diagnostics.billing_preflight import (
    format_billing_preflight_report,
    get_cached_billing_preflight,
    get_cached_billing_preflight_text,
)
from app.storage.factory import get_storage

logger = logging.getLogger(__name__)
_BOOT_REPORT_KEY = "_diagnostics/boot.json"
_BILLING_PREFLIGHT_KEY = "_diagnostics/billing_preflight.json"


def _env_set(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _git_version() -> str:
    for key in ("RENDER_GIT_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:7]
    return "unknown"


async def _db_status() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    result = await check_db_health(database_url, timeout_s=1.5)
    if result.ok:
        return "✅ ok"
    error_details = f"{result.error_class}: {result.error_message}" if result.error_class else "unknown"
    return f"❌ error ({error_details}, corr={result.correlation_id})"


async def _redis_status() -> str:
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return "⚪ not configured"
    try:
        import redis.asyncio as redis  # type: ignore

        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        if hasattr(client, "close"):
            await client.close()
        return "✅ ok"
    except Exception as exc:
        logger.warning("admin diagnostics Redis check failed: %s", exc)
        return "❌ error"


def _storage_mode(storage: object) -> str:
    name = storage.__class__.__name__.lower()
    if "postgres" in name:
        return "postgres"
    if "github" in name:
        return "github"
    if "hybrid" in name:
        return "hybrid"
    if "json" in name:
        return "json"
    return "unknown"


def _storage_tenant_check(storage: object, bot_instance_id: str) -> str:
    if not bot_instance_id:
        return "❌ missing BOT_INSTANCE_ID"

    def _check_instance(obj: object) -> tuple[bool, str]:
        if hasattr(obj, "partner_id"):
            partner_id = str(getattr(obj, "partner_id") or "")
            return (partner_id == bot_instance_id, f"partner_id={partner_id or 'missing'}")
        config = getattr(obj, "config", None)
        if config and hasattr(config, "bot_instance_id"):
            value = str(getattr(config, "bot_instance_id") or "")
            return (value == bot_instance_id, f"bot_instance_id={value or 'missing'}")
        data_dir = getattr(obj, "data_dir", None)
        if data_dir:
            dir_text = str(data_dir)
            scoped = bot_instance_id in dir_text.split("/")
            return (scoped, f"data_dir={dir_text}")
        return (False, "tenant_scope=unknown")

    if hasattr(storage, "_primary") and hasattr(storage, "_runtime"):
        primary_ok, primary_note = _check_instance(getattr(storage, "_primary"))
        runtime_ok, runtime_note = _check_instance(getattr(storage, "_runtime"))
        if primary_ok and runtime_ok:
            return f"✅ ok ({primary_note}, {runtime_note})"
        return f"❌ mismatch ({primary_note}, {runtime_note})"

    ok, note = _check_instance(storage)
    return f"✅ ok ({note})" if ok else f"❌ mismatch ({note})"


def _format_env_status(keys: List[str]) -> str:
    return ", ".join(f"{key}={'SET' if _env_set(key) else 'NOT SET'}" for key in keys)


async def _load_boot_report_text() -> Optional[str]:
    cached_text = get_cached_boot_report_text()
    if cached_text:
        return cached_text
    cached_report = get_cached_boot_report()
    if cached_report:
        return format_boot_report(cached_report)
    try:
        storage = get_storage()
        report = await storage.read_json_file(_BOOT_REPORT_KEY, default={})
    except Exception as exc:
        logger.warning("admin diagnostics boot report fetch failed: %s", exc)
        return None
    if not report:
        return None
    return format_boot_report(report)


async def _load_billing_preflight_text() -> Optional[str]:
    cached_text = get_cached_billing_preflight_text()
    if cached_text:
        return cached_text
    cached_report = get_cached_billing_preflight()
    if cached_report:
        return format_billing_preflight_report(cached_report)
    try:
        storage = get_storage()
        report = await storage.read_json_file(_BILLING_PREFLIGHT_KEY, default={})
    except Exception as exc:
        logger.warning("admin diagnostics billing preflight fetch failed: %s", exc)
        return None
    if not report:
        return None
    return format_billing_preflight_report(report)


async def build_admin_diagnostics_report() -> str:
    bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
    webhook_base_raw = os.getenv("WEBHOOK_BASE_URL", "").strip()
    webhook_base = normalize_webhook_base_url(webhook_base_raw)
    env_status = _format_env_status(
        ["TELEGRAM_BOT_TOKEN", "ADMIN_ID", "BOT_INSTANCE_ID", "WEBHOOK_BASE_URL", "KIE_API_KEY"]
    )
    storage = get_storage()
    storage_mode = _storage_mode(storage)
    tenant_check = _storage_tenant_check(storage, bot_instance_id)
    db_status = await _db_status()
    redis_status = await _redis_status()
    boot_report_text = await _load_boot_report_text()
    billing_preflight_text = await _load_billing_preflight_text()
    lines = [
        "🧭 <b>Partner diagnostics</b>",
        f"• BOT_INSTANCE_ID: <code>{bot_instance_id or 'missing'}</code>",
        f"• BOT_MODE: <code>{os.getenv('BOT_MODE', 'polling')}</code>",
        f"• ALLOW_REAL_GENERATION: <code>{os.getenv('ALLOW_REAL_GENERATION', '1')}</code>",
        f"• TEST_MODE: <code>{os.getenv('TEST_MODE', '0')}</code>",
        f"• STORAGE backend: {storage_mode}",
        f"• DB: {db_status}",
        f"• Redis: {redis_status}",
        f"• Tenant scope: {tenant_check}",
        f"• WEBHOOK_BASE_URL: <code>{webhook_base or webhook_base_raw or 'missing'}</code>",
        f"• ENV: {env_status}",
        f"• Version: <code>{_git_version()}</code>",
    ]
    if boot_report_text:
        lines.append("")
        lines.append("🧾 <b>Boot report</b>")
        lines.append(boot_report_text)

    if billing_preflight_text:
        lines.append("")
        lines.append("💳 <b>Billing preflight</b>")
        lines.append(billing_preflight_text)

    diagnostics = validate_config(strict=False)
    hints: List[str] = []
    for name in diagnostics.missing_required:
        hints.append(f"Set {name} in Render ENV and redeploy.")
    for name in diagnostics.invalid_required:
        hints.append(f"Fix {name} formatting and redeploy.")

    if not webhook_base_raw:
        hints.append("WEBHOOK_BASE_URL is missing. Example: https://your-service.onrender.com")
    elif webhook_base_raw and webhook_base_raw != webhook_base:
        hints.append("WEBHOOK_BASE_URL has extra slashes; normalize to base URL without trailing '/'.")

    if not _env_set("KIE_API_KEY"):
        hints.append("KIE_API_KEY is not set: AI generation will be disabled until provided.")

    if db_status.startswith("❌"):
        hints.append("Database is not reachable. Verify DATABASE_URL and DB availability.")

    if hints:
        lines.append("")
        lines.append("🛠️ <b>How to fix</b>")
        for hint in hints:
            lines.append(f"• {hint}")

    return "\n".join(lines)
