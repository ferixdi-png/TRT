from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from app.config_env import normalize_webhook_base_url, validate_config
from app.storage.factory import get_storage

logger = logging.getLogger(__name__)


def _env_set(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _git_version() -> str:
    for key in ("RENDER_GIT_COMMIT", "GIT_COMMIT", "COMMIT_SHA"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:7]
    return "unknown"


async def _db_status() -> str:
    try:
        storage = get_storage()
        if hasattr(storage, "ping") and asyncio.iscoroutinefunction(storage.ping):
            ok = await storage.ping()
        else:
            ok = storage.test_connection()
        return "✅ ok" if ok else "❌ error"
    except Exception as exc:
        logger.warning("admin diagnostics DB check failed: %s", exc)
        return f"❌ error ({str(exc)[:60]})"


def _redis_status() -> str:
    return "✅ ok" if os.getenv("REDIS_URL", "").strip() else "⚪ not configured"


def _format_env_status(keys: List[str]) -> str:
    return ", ".join(f"{key}={'SET' if _env_set(key) else 'NOT SET'}" for key in keys)


async def build_admin_diagnostics_report() -> str:
    bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
    webhook_base_raw = os.getenv("WEBHOOK_BASE_URL", "").strip()
    webhook_base = normalize_webhook_base_url(webhook_base_raw)
    env_status = _format_env_status(
        ["TELEGRAM_BOT_TOKEN", "ADMIN_ID", "BOT_INSTANCE_ID", "WEBHOOK_BASE_URL", "KIE_API_KEY"]
    )
    db_status = await _db_status()
    redis_status = _redis_status()
    lines = [
        "🧭 <b>Partner diagnostics</b>",
        f"• BOT_INSTANCE_ID: <code>{bot_instance_id or 'missing'}</code>",
        f"• BOT_MODE: <code>{os.getenv('BOT_MODE', 'polling')}</code>",
        f"• ALLOW_REAL_GENERATION: <code>{os.getenv('ALLOW_REAL_GENERATION', '1')}</code>",
        f"• TEST_MODE: <code>{os.getenv('TEST_MODE', '0')}</code>",
        "• STORAGE backend: db-only",
        f"• DB: {db_status}",
        f"• Redis: {redis_status}",
        f"• WEBHOOK_BASE_URL: <code>{webhook_base or webhook_base_raw or 'missing'}</code>",
        f"• ENV: {env_status}",
        f"• Version: <code>{_git_version()}</code>",
    ]

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
