"""Render entrypoint.

Goals:
- Webhook-first runtime (Render Web Service)
- aiogram-only import surface (no python-telegram-bot imports from this module)
- Health endpoints for Render + UptimeRobot
- Singleton advisory lock support (PostgreSQL) to avoid double-processing

This project historically had a PTB (python-telegram-bot) runner. Tests still cover
that legacy in bot_kie.py, but this runtime is aiogram-based.

Important: the repo contains a local ./aiogram folder with tiny test stubs.
In production we must import the real aiogram package from site-packages.
"""

from __future__ import annotations

import contextlib
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import json

from aiohttp import web

from app.storage import get_storage
from app.storage.status import normalize_job_status
from app.utils.logging_config import setup_logging  # noqa: E402
from app.utils.orphan_reconciler import OrphanCallbackReconciler  # PHASE 5
from app.utils.runtime_state import runtime_state  # noqa: E402
from app.utils.webhook import (
    build_kie_callback_url,
    get_kie_callback_path,
    get_webhook_base_url,
    get_webhook_secret_token,
)  # noqa: E402

def _import_real_aiogram_symbols():
    """Import aiogram symbols from site-packages even if ./aiogram stubs exist."""
    project_root = Path(__file__).resolve().parent
    has_local_stubs = (project_root / "aiogram" / "__init__.py").exists()
    removed: list[str] = []

    if has_local_stubs:
        # Remove project root and '' so import machinery does not pick local stubs.
        for entry in list(sys.path):
            if entry in {"", str(project_root)}:
                removed.append(entry)
                try:
                    sys.path.remove(entry)
                except ValueError:
                    pass

    try:
        # Import the package (this will populate sys.modules with the real aiogram).
        import importlib

        importlib.import_module("aiogram")
    finally:
        # Restore path for app imports.
        for entry in reversed(removed):
            sys.path.insert(0, entry)

    # Now import symbols from whichever aiogram got loaded.
    from aiogram import Bot, Dispatcher  # type: ignore
    from aiogram.fsm.storage.memory import MemoryStorage  # type: ignore
    from aiogram.types import Update  # type: ignore
    from aiogram.client.default import DefaultBotProperties  # type: ignore

    return Bot, Dispatcher, MemoryStorage, Update, DefaultBotProperties


Bot, Dispatcher, MemoryStorage, Update, DefaultBotProperties = _import_real_aiogram_symbols()


logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _derive_secret_path_from_token(token: str) -> str:
    """Derive a stable URL-safe secret path.

    Compatibility note:
    Older deployments used the bot token with ':' removed as the webhook path.
    We keep that behavior as the default to avoid silent 404s after redeploys.
    """

    cleaned = token.strip().replace(":", "")
    # Keep it reasonably short but stable.
    if len(cleaned) > 64:
        cleaned = cleaned[-64:]
    return cleaned


@dataclass(frozen=True)
class RuntimeConfig:
    bot_mode: str
    port: int
    webhook_base_url: str
    webhook_secret_path: str
    webhook_secret_token: str
    telegram_bot_token: str
    database_url: str
    dry_run: bool
    kie_callback_path: str
    kie_callback_token: str


def _load_runtime_config() -> RuntimeConfig:
    bot_mode = os.getenv("BOT_MODE", "webhook").strip().lower()
    port_env = os.getenv("PORT")
    port = int(port_env) if port_env else 0
    webhook_base_url = get_webhook_base_url().strip().rstrip("/")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    # Secret path in URL (preferred). Can be explicitly overridden.
    webhook_secret_path = os.getenv("WEBHOOK_SECRET_PATH", "").strip()
    if not webhook_secret_path:
        webhook_secret_path = _derive_secret_path_from_token(telegram_bot_token)

    # Secret token in header (Telegram supports X-Telegram-Bot-Api-Secret-Token)
    webhook_secret_token = get_webhook_secret_token()

    database_url = os.getenv("DATABASE_URL", "").strip()
    dry_run = _bool_env("DRY_RUN", False) or _bool_env("TEST_MODE", False)
    kie_callback_path = get_kie_callback_path()
    kie_callback_token = os.getenv("KIE_CALLBACK_TOKEN", "").strip()

    return RuntimeConfig(
        bot_mode=bot_mode,
        port=port,
        webhook_base_url=webhook_base_url,
        webhook_secret_path=webhook_secret_path,
        webhook_secret_token=webhook_secret_token,
        telegram_bot_token=telegram_bot_token,
        database_url=database_url,
        dry_run=dry_run,
        kie_callback_path=kie_callback_path,
        kie_callback_token=kie_callback_token,
    )


@dataclass
class ActiveState:
    active: bool


class SingletonLock:
    """Async wrapper for the sync advisory lock implementation."""

    def __init__(self, database_url: str, *, key: Optional[int] = None):
        self.database_url = database_url
        self.key = key
        self._acquired = False

    async def acquire(self, timeout: float | None = None) -> bool:
        # NOTE: app.locking.single_instance.acquire_single_instance_lock() reads DATABASE_URL
        # from env and uses the psycopg2 pool from database.py. We keep this wrapper async
        # for uniformity.
        if not self.database_url:
            self._acquired = True
            return True

        try:
            from app.locking.single_instance import acquire_single_instance_lock

            # Signature has no args (it reads env). Run in thread with optional timeout
            if timeout is not None:
                try:
                    # Fast non-blocking acquire with timeout
                    self._acquired = bool(
                        await asyncio.wait_for(
                            asyncio.to_thread(acquire_single_instance_lock),
                            timeout=timeout
                        )
                    )
                    return self._acquired
                except asyncio.TimeoutError:
                    logger.debug("[LOCK] Acquire timed out after %.1fs", timeout)
                    self._acquired = False
                    return False
            else:
                # No timeout - blocking acquire
                self._acquired = bool(await asyncio.to_thread(acquire_single_instance_lock))
                return self._acquired
        except Exception as e:
            logger.exception("[LOCK] Failed to acquire singleton lock: %s", e)
            self._acquired = False
            return False

    async def release(self) -> None:
        if not self.database_url:
            return
        if not self._acquired:
            return
        try:
            from app.locking.single_instance import release_single_instance_lock

            release_single_instance_lock()
        except Exception as e:
            logger.warning("[LOCK] Failed to release singleton lock: %s", e)


# Exported name for tests (they monkeypatch this)
try:
    from app.storage.pg_storage import PostgresStorage
except Exception:  # pragma: no cover
    PostgresStorage = object  # type: ignore


async def preflight_webhook(bot: Bot) -> None:
    """Remove webhook to avoid conflict when running polling."""
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("[PRE-FLIGHT] Webhook deleted")
    except Exception as e:
        logger.warning("[PRE-FLIGHT] Failed to delete webhook: %s", e)


def create_bot_application() -> tuple[Dispatcher, Bot]:
    """Create aiogram Dispatcher + Bot (sync factory for tests)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    # aiogram 3.7.0+ requires DefaultBotProperties for parse_mode
    default_properties = DefaultBotProperties(parse_mode="HTML")
    bot = Bot(token=token, default=default_properties)
    dp = Dispatcher(storage=MemoryStorage())

    # Routers
    from bot.handlers import (
        admin_router,
        balance_router,
        diag_router,
        error_handler_router,
        flow_router,
        gallery_router,
        history_router,
        marketing_router,
        quick_actions_router,
        zero_silence_router,
    )

    dp.include_router(error_handler_router)
    dp.include_router(diag_router)
    dp.include_router(admin_router)
    dp.include_router(balance_router)
    dp.include_router(history_router)
    dp.include_router(marketing_router)
    dp.include_router(gallery_router)
    dp.include_router(quick_actions_router)
    dp.include_router(flow_router)
    dp.include_router(zero_silence_router)

    return dp, bot


async def verify_bot_identity(bot: Bot) -> None:
    """Verify bot identity and webhook configuration.
    
    Logs bot.getMe() and getWebhookInfo() to ensure correct bot/token/webhook.
    Prevents issues like "wrong bot deployed" or "webhook pointing to old URL".
    """
    try:
        me = await bot.get_me()
        logger.info(
            "[BOT_VERIFY] ✅ Bot identity: @%s (id=%s, name='%s')",
            me.username, me.id, me.first_name
        )
    except Exception as exc:
        logger.error("[BOT_VERIFY] ❌ Failed to get bot info: %s", exc)
        raise

    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.info(
                "[BOT_VERIFY] 📡 Webhook: %s (pending=%s, last_error=%s)",
                webhook_info.url,
                webhook_info.pending_update_count,
                webhook_info.last_error_message or "none"
            )
        else:
            logger.info("[BOT_VERIFY] 📡 No webhook configured (polling mode or not set yet)")
    except Exception as exc:
        logger.warning("[BOT_VERIFY] ⚠️ Failed to get webhook info: %s", exc)


def _build_webhook_url(cfg: RuntimeConfig) -> str:
    base = cfg.webhook_base_url.rstrip("/")
    return f"{base}/webhook/{cfg.webhook_secret_path}" if base else ""


def _build_kie_callback_url(cfg: RuntimeConfig) -> str:
    return build_kie_callback_url(cfg.webhook_base_url, cfg.kie_callback_path)


def _health_payload(active_state: ActiveState) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "active" if active_state.active else "passive",
        "active": bool(active_state.active),
        "bot_mode": runtime_state.bot_mode,
        "storage_mode": runtime_state.storage_mode,
        "lock_acquired": runtime_state.lock_acquired,
        "instance_id": runtime_state.instance_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _make_web_app(
    *,
    dp: Dispatcher,
    bot: Bot,
    cfg: RuntimeConfig,
    active_state: ActiveState,
) -> web.Application:
    app = web.Application()
    # In-memory resilience structures (single instance assumption)
    recent_update_ids: set[int] = set()
    rate_map: dict[str, list[float]] = {}

    def _client_ip(request: web.Request) -> str:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return ip or (request.remote or "unknown")

    def _rate_limited(ip: str, now: float, limit: int = 5, window_s: float = 1.0) -> bool:
        hits = rate_map.get(ip, [])
        hits = [t for t in hits if now - t <= window_s]
        if len(hits) >= limit:
            rate_map[ip] = hits
            return True
        hits.append(now)
        rate_map[ip] = hits
        return False

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def root(_request: web.Request) -> web.Response:
        return web.json_response(_health_payload(active_state))

    async def webhook(request: web.Request) -> web.Response:
        """Webhook handler with full validation and error handling.
        
        Security:
        - Verifies webhook secret path
        - Validates X-Telegram-Bot-Api-Secret-Token header
        - Rate limits and protects against malformed payloads
        
        Errors:
        - 400: Malformed JSON
        - 401: Invalid secret token
        - 404: Invalid path (hides existence)
        - 503: Instance not ready (during rolling deploy)
        - 200: OK (even if processing failed - Telegram will retry)
        """
        secret = request.match_info.get("secret")
        if secret != cfg.webhook_secret_path:
            # Hide existence of endpoint
            raise web.HTTPNotFound()

        # Enforce Telegram header secret if configured
        if cfg.webhook_secret_token:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != cfg.webhook_secret_token:
                logger.warning("[WEBHOOK] Invalid secret token")
                raise web.HTTPUnauthorized()

        if not active_state.active:
            # 🎯 PASSIVE MODE: Throttled user notifications via controller
            try:
                payload = await request.json()
                update = Update.model_validate(payload)
                
                # Extract chat_id
                chat_id = None
                if update.message:
                    chat_id = update.message.chat.id
                elif update.callback_query:
                    chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
                
                # Controller handles throttling (max 1 per 60s)
                if chat_id and hasattr(active_state, 'lock_controller'):
                    await active_state.lock_controller.send_passive_notice_if_needed(chat_id)
            except Exception as e:
                logger.debug(f"[PASSIVE MODE] Could not parse update: {e}")
            
            return web.Response(status=200, text="ok")

        # Basic rate limiting per IP
        ip = _client_ip(request)
        now = time.time()
        if _rate_limited(ip, now):
            logger.warning("[WEBHOOK] Rate limit exceeded for ip=%s", ip)
            return web.Response(status=200, text="ok")

        # Parse JSON with timeout protection
        try:
            try:
                payload = await asyncio.wait_for(
                    request.json(),
                    timeout=5.0  # 5 second timeout for JSON parsing
                )
            except asyncio.TimeoutError:
                logger.warning("[WEBHOOK] JSON parsing timeout")
                return web.Response(status=400, text="timeout")
        except Exception as e:
            logger.warning("[WEBHOOK] Bad JSON: %s", e)
            return web.Response(status=400, text="bad json")

        # Process update with error isolation and duplicate suppression
        try:
            try:
                update = Update.model_validate(payload)
            except Exception as e:
                logger.warning("[WEBHOOK] Invalid Telegram update: %s", e)
                return web.Response(status=400, text="invalid update")
            
            try:
                update_id = int(getattr(update, "update_id", 0))
            except Exception:
                update_id = 0
            if update_id and update_id in recent_update_ids:
                logger.info("[WEBHOOK] Duplicate update_id=%s ignored", update_id)
                return web.Response(status=200, text="ok")

            # Feed update to dispatcher with timeout
            try:
                await asyncio.wait_for(
                    dp.feed_update(bot, update),
                    timeout=30.0  # 30 second timeout for update processing
                )
            except asyncio.TimeoutError:
                logger.error("[WEBHOOK] Update processing timeout for update_id=%s", 
                           update.update_id)
                # Still return 200 - Telegram will retry if needed
            except Exception as e:
                logger.exception("[WEBHOOK] Error processing update_id=%s: %s",
                               update.update_id, e)
                # Still return 200 - prevent Telegram storm
            else:
                if update_id:
                    recent_update_ids.add(update_id)
        except Exception as e:
            logger.exception("[WEBHOOK] Unexpected error: %s", e)
            # 200 to prevent Telegram retry storm; errors are logged for monitoring
        
        return web.Response(status=200, text="ok")

    async def _send_generation_result(bot: Bot, chat_id: int, result_urls: list[str], task_id: str) -> None:
        """
        Smart sender: detect content type and send appropriately.
        
        Handles:
        - Single/multiple images → sendPhoto/sendMediaGroup
        - Videos → sendVideo
        - Audio → sendAudio
        - Documents/files → sendDocument
        - Text/unknown → sendMessage with URLs
        """
        if not result_urls:
            return
        
        try:
            # Detect content type from URLs
            image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
            video_exts = {'.mp4', '.avi', '.mov', '.webm', '.mkv'}
            audio_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
            
            classified = {'images': [], 'videos': [], 'audio': [], 'other': []}
            
            for url in result_urls:
                url_lower = url.lower()
                if any(url_lower.endswith(ext) for ext in image_exts):
                    classified['images'].append(url)
                elif any(url_lower.endswith(ext) for ext in video_exts):
                    classified['videos'].append(url)
                elif any(url_lower.endswith(ext) for ext in audio_exts):
                    classified['audio'].append(url)
                else:
                    classified['other'].append(url)
            
            # Send based on classification
            if classified['images']:
                if len(classified['images']) == 1:
                    # Single image
                    await bot.send_photo(chat_id, classified['images'][0], 
                                        caption=f"✅ Генерация готова\\nID: {task_id}")
                else:
                    # Multiple images - send as album (max 10 per Telegram limit)
                    from aiogram.types import InputMediaPhoto
                    media_group = [
                        InputMediaPhoto(media=url, caption=f"✅ {i+1}/{len(classified['images'])}")
                        for i, url in enumerate(classified['images'][:10])
                    ]
                    await bot.send_media_group(chat_id, media=media_group)
                    
                    # If more than 10, send rest as messages
                    if len(classified['images']) > 10:
                        remaining = "\\n".join(classified['images'][10:])
                        await bot.send_message(chat_id, f"Ещё {len(classified['images'])-10} изображений:\\n{remaining}")
            
            if classified['videos']:
                for video_url in classified['videos']:
                    await bot.send_video(chat_id, video_url, caption=f"✅ Видео готово\\nID: {task_id}")
            
            if classified['audio']:
                for audio_url in classified['audio']:
                    await bot.send_audio(chat_id, audio_url, caption=f"✅ Аудио готово\\nID: {task_id}")
            
            if classified['other']:
                # Unknown type - send as message with links
                text = f"✅ Генерация готова\\nID: {task_id}\\n\\n" + "\\n".join(classified['other'])
                await bot.send_message(chat_id, text)
                
        except Exception as e:
            # Fallback: send as plain text message
            logger.exception(f"[TELEGRAM_SENDER] Failed smart send, falling back to text: {e}")
            text = f"✅ Генерация готова (ссылки)\\nID: {task_id}\\n\\n" + "\\n".join(result_urls)
            await bot.send_message(chat_id, text)

    async def kie_callback(request: web.Request) -> web.Response:
        """
        KIE callback handler - ALWAYS returns 200 to prevent retry storms.
        Handles malformed payloads gracefully.
        """
        # Token validation
        if cfg.kie_callback_token:
            header = request.headers.get("X-KIE-Callback-Token", "")
            if header != cfg.kie_callback_token:
                logger.warning("[KIE_CALLBACK] Invalid token")
                # Still return 200 to prevent retries
                return web.json_response({"ok": False, "error": "invalid_token"}, status=200)

        # Import robust parser
        from app.utils.callback_parser import extract_task_id, safe_truncate_payload
        
        # Parse payload with maximum tolerance
        raw_payload = None
        try:
            raw_payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            # Try reading raw bytes
            try:
                raw_payload = await request.read()
                logger.warning("[KIE_CALLBACK] JSON parse failed, got bytes: %d bytes, error: %s",
                              len(raw_payload) if raw_payload else 0, exc)
            except Exception as read_exc:  # noqa: BLE001
                logger.warning("[KIE_CALLBACK] Could not read payload: %s", read_exc)
                # Still return 200
                return web.json_response({"ok": True, "ignored": True, "reason": "unreadable_payload"}, status=200)
        
        # Extract task ID using robust parser
        query_params = dict(request.query) if request.query else None
        headers = dict(request.headers) if request.headers else None
        
        task_id, record_id, debug_info = extract_task_id(raw_payload, query_params, headers)
        
        if not task_id and not record_id:
            # Log warning with safe payload preview
            payload_preview = safe_truncate_payload(raw_payload, max_length=300)
            logger.warning(
                "[KIE_CALLBACK] No taskId/recordId found. "
                "Debug: %s | Payload preview: %s",
                debug_info, payload_preview
            )
            # Still return 200 to prevent retry storm
            return web.json_response({
                "ok": True,
                "ignored": True,
                "reason": "no_task_id",
                "debug": debug_info
            }, status=200)
        
        # Use task_id or record_id (prefer task_id)
        effective_id = task_id or record_id
        logger.info("[KIE_CALLBACK] Received callback for task_id=%s (record_id=%s) via %s",
                   task_id, record_id, debug_info.get("extraction_path", []))
        
        # Parse payload as dict for further processing
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        if not payload and raw_payload:
            try:
                if isinstance(raw_payload, bytes):
                    payload = json.loads(raw_payload.decode('utf-8'))
                elif isinstance(raw_payload, str):
                    payload = json.loads(raw_payload)
            except Exception:  # noqa: BLE001
                pass  # Continue with empty dict

        state = payload.get("state") or payload.get("status")
        result_urls = payload.get("resultUrls") or payload.get("result_urls") or []
        result_json = payload.get("resultJson") or payload.get("result_json")
        if not result_urls and isinstance(result_json, str):
            try:
                parsed = json.loads(result_json)
                result_urls = parsed.get("resultUrls") or parsed.get("urls") or []
            except Exception as exc:  # noqa: BLE001
                logger.debug("[KIE_CALLBACK] resultJson parse failed: %s", exc)
        error_text = payload.get("failMsg") or payload.get("errorMessage") or payload.get("error")

        normalized_status = normalize_job_status(state or ("done" if result_urls else "running"))

        storage = get_storage()
        job = None
        try:
            job = await storage.get_job(effective_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[KIE_CALLBACK] get_job failed: %s", exc)

        if not job and hasattr(storage, "find_job_by_task_id"):
            try:
                job = await storage.find_job_by_task_id(effective_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[KIE_CALLBACK] find_job_by_task_id failed: %s", exc)

        if job:
            job_id = job.get("job_id") or job.get("id") or effective_id
            try:
                await storage.update_job_status(
                    job_id,
                    normalized_status,
                    result_urls=result_urls or None,
                    error_message=error_text,
                )
                logger.info("[KIE_CALLBACK] Updated job %s to status=%s", job_id, normalized_status)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[KIE_CALLBACK] Failed to update job %s: %s", job_id, exc)

            # 🎯 TELEGRAM DELIVERY (guaranteed delivery)
            user_id = job.get("user_id")
            # Get chat_id from job params (more reliable for delivery)
            chat_id = user_id  # Default fallback
            if job.get("params"):
                job_params = job.get("params")
                if isinstance(job_params, dict):
                    chat_id = job_params.get("chat_id") or user_id
                elif isinstance(job_params, str):
                    try:
                        params_dict = json.loads(job_params)
                        chat_id = params_dict.get("chat_id") or user_id
                    except Exception:  # noqa: BLE001
                        pass
            
            if user_id and chat_id:
                try:
                    if normalized_status == "done" and result_urls:
                        # 🎯 Smart sender: detect content type and send appropriately
                        await _send_generation_result(bot, chat_id, result_urls, effective_id)
                        logger.info(f"[KIE_CALLBACK] ✅ Sent result to chat_id={chat_id} user_id={user_id}")
                        
                        # Mark as delivered (prevents duplicates)
                        try:
                            await storage.update_job_status(job_id, 'done', delivered=True)
                        except Exception:
                            pass  # Best effort - job still delivered
                    elif normalized_status == "done" and not result_urls:
                        # Success but no URLs - this is suspicious
                        text = f"⚠️ Генерация завершилась, но результат пуст. ID: {effective_id}"
                        await bot.send_message(chat_id, text)
                        logger.warning(f"[KIE_CALLBACK] ⚠️ Empty result for task {effective_id}")
                    elif normalized_status == "failed":
                        text = f"❌ Генерация не завершилась: {error_text or 'Ошибка'}\\nID: {effective_id}"
                        await bot.send_message(chat_id, text)
                        logger.info(f"[KIE_CALLBACK] ❌ Sent error to chat_id={chat_id} user_id={user_id}")
                    else:
                        # Don't spam intermediate statuses
                        logger.debug(f"[KIE_CALLBACK] Intermediate status {normalized_status} for task {effective_id}")
                except Exception as exc:  # noqa: BLE001
                    logger.exception("[KIE_CALLBACK] Failed to send to user %s: %s", user_id, exc)
                    runtime_state.telegram_send_fail_count += 1
        else:
            # 🎯 ORPHAN JOB: Callback arrived but no job in DB (PHASE 4 FIX)
            logger.warning(
                "[KIE_CALLBACK] ⚠️ ORPHAN CALLBACK | task_id=%s record_id=%s status=%s | "
                "Callback arrived before job creation - saving for reconciliation",
                task_id, record_id, state
            )
            runtime_state.callback_job_not_found_count += 1
            
            # PHASE 4: Save orphan callback for later reconciliation
            # Instead of trying to create job with user_id=0 (which fails FK)
            try:
                orphan_payload = {
                    'task_id': effective_id,
                    'state': state,
                    'result_urls': result_urls,
                    'error_text': error_text,
                    'normalized_status': normalized_status,
                    'full_payload': payload,
                    'received_at': datetime.now().isoformat()
                }
                
                # Save to orphan_callbacks table
                await storage._save_orphan_callback(effective_id, orphan_payload)
                logger.info(f"[KIE_CALLBACK] Saved orphan callback for task_id={effective_id}")
            except Exception as exc:
                logger.exception("[KIE_CALLBACK] Failed to save orphan callback: %s", exc)
            
            # Try to create orphan job retroactively (best effort)
            if runtime_state.db_schema_ready and hasattr(storage, "add_generation_job"):
                try:
                    orphan_job_id = effective_id
                    await storage.add_generation_job(
                        user_id=0,  # Unknown user
                        model_id="unknown",
                        model_name="orphan",
                        params={"orphan": True, "payload": safe_truncate_payload(payload, 1000)},
                        price=0.0,
                        task_id=effective_id,
                        status=normalized_status
                    )
                    # Update with result
                    await storage.update_job_status(
                        orphan_job_id,
                        normalized_status,
                        result_urls=result_urls or None,
                        error_message=error_text or "Orphan job - no original request found"
                    )
                    logger.info(f"[KIE_CALLBACK] Created orphan job {orphan_job_id}")
                except Exception as e:
                    logger.error(f"[KIE_CALLBACK] Failed to create orphan job: {e}")

        # ALWAYS return 200 to prevent KIE retry storms
        return web.json_response({"ok": True}, status=200)

    callback_route = f"/{cfg.kie_callback_path.lstrip('/')}"
    app.router.add_get("/health", health)
    app.router.add_get("/", root)
    # aiohttp auto-registers HEAD for GET; explicit add_head causes duplicate route
    app.router.add_post(callback_route, kie_callback)
    app.router.add_post("/webhook/{secret}", webhook)

    async def on_shutdown(_app: web.Application) -> None:
        await bot.session.close()

    app.on_shutdown.append(on_shutdown)
    return app


async def _start_web_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner


async def main() -> None:
    LOG_LEVEL_ENV = os.getenv("LOG_LEVEL", "").upper()
    setup_logging(level=(logging.DEBUG if LOG_LEVEL_ENV == "DEBUG" else logging.INFO))

    cfg = _load_runtime_config()
    effective_bot_mode = cfg.bot_mode
    if effective_bot_mode == "webhook" and not cfg.webhook_base_url:
        logger.warning(
            "[CONFIG] WEBHOOK_BASE_URL missing in webhook mode; falling back to polling"
        )
        effective_bot_mode = "polling"

    runtime_state.bot_mode = effective_bot_mode
    runtime_state.last_start_time = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("STARTUP (aiogram)")
    logger.info("BOT_MODE=%s PORT=%s", effective_bot_mode, cfg.port or "(not set)")
    logger.info("WEBHOOK_BASE_URL=%s", cfg.webhook_base_url or "(not set)")
    logger.info("WEBHOOK_SECRET_PATH=%s", (cfg.webhook_secret_path[:6] + "..."))
    logger.info("WEBHOOK_SECRET_TOKEN=%s", "SET" if cfg.webhook_secret_token else "(not set)")
    logger.info("KIE_CALLBACK_PATH=%s", cfg.kie_callback_path)
    logger.info("KIE_CALLBACK_TOKEN=%s", "SET" if cfg.kie_callback_token else "(not set)")
    logger.info("DRY_RUN=%s", cfg.dry_run)
    logger.info("=" * 60)

    dp, bot = create_bot_application()
    
    # Verify bot identity and webhook configuration BEFORE anything else
    await verify_bot_identity(bot)

    # IMPORTANT: the advisory lock helper in app.locking.single_instance relies on
    # the psycopg2 connection pool from database.py being initialized.
    # If we don't create the pool first, lock acquisition can fail even when no
    # other instance is running, leaving this deploy permanently PASSIVE.
    #
    # SINGLETON_LOCK_FORCE_ACTIVE (default: 1 / True for Render)
    #   - When True: if lock acquisition fails, proceed as ACTIVE anyway
    #     (assumes only one Render Web Service instance)
    #   - When False: don't proceed if lock acquisition fails
    #
    # SINGLETON_LOCK_STRICT (default: 0)
    #   - When True: exit immediately if lock acquisition fails
    #   - When False: continue in PASSIVE mode if lock acquisition fails
    if cfg.database_url:
        try:
            from database import get_connection_pool

            get_connection_pool()
        except Exception as e:
            logger.warning("[DB] Could not initialize psycopg2 pool for lock: %s", e)
    else:
        # No database URL - using JSON storage
        runtime_state.db_schema_ready = True  # JSON storage doesn't need migrations

    # Create lock object and state tracker
    lock = SingletonLock(cfg.database_url)
    active_state = ActiveState(active=False)  # Start as passive, will activate after lock
    
    # 🔧 BACKGROUND TASKS: migrations + lock acquisition (NON-BLOCKING)
    # This ensures HTTP server starts IMMEDIATELY without waiting
    async def background_initialization():
        """Initialize database schema and acquire lock in background."""
        # Step 1: Apply migrations (non-blocking)
        if cfg.database_url:
            logger.info("[BACKGROUND] Applying database migrations...")
            try:
                from app.storage.migrations import apply_migrations_safe
                migrations_ok = await apply_migrations_safe(cfg.database_url)
                if migrations_ok:
                    logger.info("[MIGRATIONS] ✅ Database schema ready")
                    runtime_state.db_schema_ready = True
                else:
                    logger.error("[MIGRATIONS] ❌ Schema NOT ready")
                    runtime_state.db_schema_ready = False
            except Exception as e:
                logger.exception(f"[MIGRATIONS] CRITICAL: Auto-apply failed: {e}")
                runtime_state.db_schema_ready = False
        else:
            runtime_state.db_schema_ready = True
        
        # PHASE 5: Start orphan callback reconciliation background task
        if runtime_state.db_schema_ready and cfg.database_url:
            try:
                # Create storage instance for reconciler
                from app.storage import get_storage
                storage_instance = get_storage()
                
                reconciler = OrphanCallbackReconciler(
                    storage=storage_instance,
                    bot=bot,
                    check_interval=10,
                    max_age_minutes=30
                )
                await reconciler.start()
                logger.info("[RECONCILER] ✅ Background orphan reconciliation started (10s interval, 30min timeout)")
            except Exception as exc:
                logger.warning(f"[RECONCILER] ⚠️ Failed to start reconciler: {exc}")
        
        # PHASE 6: CRITICAL - Setup webhook IMMEDIATELY (before lock acquisition)
        # This ensures webhook is configured even if lock callback has race conditions
        if effective_bot_mode == "webhook" and not cfg.dry_run:
            logger.info("[WEBHOOK_EARLY] 🔧 Setting up webhook BEFORE lock acquisition...")
            webhook_url = _build_webhook_url(cfg)
            if webhook_url:
                from app.utils.webhook import ensure_webhook
                try:
                    webhook_set = await ensure_webhook(
                        bot,
                        webhook_url=webhook_url,
                        secret_token=cfg.webhook_secret_token or None,
                        force_reset=True,
                    )
                    if webhook_set:
                        logger.info("[WEBHOOK_EARLY] ✅ ✅ ✅ WEBHOOK CONFIGURED (early setup)")
                    else:
                        logger.error("[WEBHOOK_EARLY] ❌ Failed to set webhook!")
                except Exception as e:
                    logger.exception("[WEBHOOK_EARLY] ❌ Exception: %s", e)
            else:
                logger.error("[WEBHOOK_EARLY] ❌ Cannot build webhook URL!")
        
        # Define init_active_services BEFORE lock_controller creation
        db_service = None
        free_manager = None

        async def init_active_services() -> None:
            """Initialize services when lock acquired (called by controller callback)"""
            nonlocal db_service, free_manager
            
            logger.info("[INIT_SERVICES] 🚀 init_active_services() CALLED")
            logger.info(f"[INIT_SERVICES] BOT_MODE={effective_bot_mode}, DRY_RUN={cfg.dry_run}")

            # Update runtime state
            active_state.active = True
            runtime_state.lock_acquired = True

            if cfg.database_url:
                logger.info("[INIT_SERVICES] Initializing DatabaseService...")
                try:
                    from app.database.services import DatabaseService
                    from app.free.manager import FreeModelManager

                    db_service = DatabaseService(cfg.database_url)
                    await db_service.initialize()
                    free_manager = FreeModelManager(db_service)

                    from bot.handlers.balance import set_database_service as set_balance_db
                    from bot.handlers.history import set_database_service as set_history_db
                    from bot.handlers.marketing import (
                        set_database_service as set_marketing_db,
                        set_free_manager,
                    )

                    set_balance_db(db_service)
                    set_history_db(db_service)
                    set_marketing_db(db_service)
                    set_free_manager(free_manager)

                    logger.info("[DB] ✅ DatabaseService initialized and injected into handlers")
                except Exception as e:
                    logger.exception("[DB] ❌ Database init failed: %s", e)
                    db_service = None
            
            logger.info(f"[ACTIVE_INIT] Webhook setup check: mode={effective_bot_mode}, dry_run={cfg.dry_run}")
            if effective_bot_mode == "webhook" and not cfg.dry_run:
                logger.info("[ACTIVE_INIT] Building webhook URL...")
                webhook_url = _build_webhook_url(cfg)
                if not webhook_url:
                    logger.error("[ACTIVE_INIT] ❌ Cannot build webhook URL!")
                    raise RuntimeError("WEBHOOK_BASE_URL is required for BOT_MODE=webhook")
                
                logger.info(f"[ACTIVE_INIT] Webhook URL built: {webhook_url[:50]}...")

                from app.utils.webhook import ensure_webhook
                
                logger.info("[WEBHOOK_SETUP] 🔧 Calling ensure_webhook (force_reset=True)...")
                try:
                    webhook_set = await ensure_webhook(
                        bot,
                        webhook_url=webhook_url,
                        secret_token=cfg.webhook_secret_token or None,
                        force_reset=True,
                    )
                    logger.info(f"[WEBHOOK_SETUP] ensure_webhook() returned: {webhook_set}")
                    
                    if not webhook_set:
                        logger.error("[WEBHOOK_SETUP] ❌ Failed to set webhook! Bot will NOT receive updates.")
                    else:
                        logger.info("[WEBHOOK_SETUP] ✅ ✅ ✅ WEBHOOK CONFIGURED SUCCESSFULLY")
                        logger.info("[WEBHOOK_SETUP] ✅ Bot will now receive /start and other commands")
                except Exception as e:
                    logger.exception("[WEBHOOK_SETUP] ❌ EXCEPTION during ensure_webhook: %s", e)
                    raise
            else:
                logger.info(f"[ACTIVE_INIT] Skipping webhook (mode={effective_bot_mode}, dry_run={cfg.dry_run})")
        
        # Step 2: Start unified lock controller with callback
        from app.locking.controller import SingletonLockController
        
        lock_controller = SingletonLockController(lock, bot, on_active_callback=init_active_services)
        active_state.lock_controller = lock_controller  # Store for webhook access
        
        await lock_controller.start()
        
        # Initial sync (if lock acquired immediately)
        active_state.active = lock_controller.should_process_updates()
        runtime_state.lock_acquired = active_state.active
        
        if active_state.active:
            logger.info("[LOCK_CONTROLLER] ✅ ACTIVE MODE (lock acquired immediately)")
        else:
            logger.info("[LOCK_CONTROLLER] ⏸️ PASSIVE MODE (background watcher started)")

    runner: Optional[web.AppRunner] = None
    
    async def state_sync_loop() -> None:
        """Periodically sync active_state with lock_controller (every 1s)"""
        while True:
            await asyncio.sleep(1)
            if hasattr(active_state, 'lock_controller'):
                new_active = active_state.lock_controller.should_process_updates()
                if new_active != active_state.active:
                    active_state.active = new_active
                    runtime_state.lock_acquired = new_active
                    if new_active:
                        logger.info("[STATE_SYNC] ✅ PASSIVE → ACTIVE (lock acquired)")
                        # Note: init_active_services already called by lock_controller callback
                        logger.info("[STATE_SYNC] Services already initialized by controller callback")

    # 🚀 START BACKGROUND INITIALIZATION (non-blocking)
    asyncio.create_task(background_initialization())
    asyncio.create_task(state_sync_loop())  # Sync active_state with controller

    try:
        if effective_bot_mode == "polling":
            # Create app and start HTTP server IMMEDIATELY
            app = _make_web_app(dp=dp, bot=bot, cfg=cfg, active_state=active_state)
            if cfg.port:
                runner = await _start_web_server(app, cfg.port)
                logger.info("[HEALTH] ✅ Server started on port %s (migrations/lock in background)", cfg.port)

            # Wait briefly for background init (but don't block)
            await asyncio.sleep(0.5)

            # If passive mode, keep healthcheck running
            if not active_state.active:
                logger.info("[PASSIVE MODE] HTTP server running, state_sync_loop monitors lock")
                await asyncio.Event().wait()
                return

            # Active mode: initialize services and start polling
            # (init_active_services called by state_sync_loop on PASSIVE→ACTIVE)
            await preflight_webhook(bot)
            await dp.start_polling(bot)
            return

        # webhook mode - START HTTP SERVER IMMEDIATELY
        app = _make_web_app(dp=dp, bot=bot, cfg=cfg, active_state=active_state)
        if cfg.port:
            runner = await _start_web_server(app, cfg.port)
            logger.info("[HEALTH] ✅ Server started on port %s (migrations/lock in background)", cfg.port)

        # Wait briefly for background init (but don't block)
        await asyncio.sleep(0.5)

        # Initialize active services if lock acquired
        # (init_active_services called by state_sync_loop on PASSIVE→ACTIVE)
        if not active_state.active:
            logger.info("[PASSIVE MODE] HTTP server running, state_sync_loop monitors lock")

        await asyncio.Event().wait()
    finally:
        try:
            if runner is not None:
                await runner.cleanup()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        try:
            if db_service is not None:
                await db_service.close()
        except Exception:
            pass
        try:
            await lock.release()
        except Exception:
            pass

        # Close sync pool used by advisory lock (best-effort)
        try:
            from database import close_connection_pool

            close_connection_pool()
        except Exception:
            pass


if __name__ == "__main__":

    asyncio.run(main())
