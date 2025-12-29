from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import setup_application

from app.utils.healthcheck import get_health_state

log = logging.getLogger("webhook")


# Media proxy cache (in-memory, TTL 10 min)
_media_proxy_cache: Dict[str, Tuple[str, datetime]] = {}
_CACHE_TTL = timedelta(minutes=10)


def _default_secret(token: str) -> str:
    # Stable secret derived from bot token (do NOT log the token).
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def mask_path(path: str) -> str:
    """Mask secret in path for logging (show first 4 and last 4 chars of secret part)."""
    if "/webhook/" in path:
        parts = path.split("/webhook/")
        if len(parts) > 1 and parts[1]:
            secret_part = parts[1].split("/")[0]  # Get secret before any additional path
            if len(secret_part) > 8:
                masked = secret_part[:4] + "****" + secret_part[-4:]
                return f"/webhook/{masked}"
    return path


def _detect_base_url() -> Optional[str]:
    # Prefer explicit config; fall back to common Render vars if present.
    for key in ("WEBHOOK_BASE_URL", "RENDER_EXTERNAL_URL", "PUBLIC_URL", "SERVICE_URL"):
        v = os.getenv(key, "").strip()
        if v:
            return v.rstrip("/")
    return None


class DispatcherWebhookHandler:
    """Webhook handler that logs requests and updates before feeding aiogram."""

    def __init__(self, dp: Dispatcher, bot: Bot):
        self.dp = dp
        self.bot = bot

    def _build_request_id(self, request: web.Request) -> str:
        return request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @staticmethod
    def _extract_update_meta(update: Update) -> Tuple[str, Optional[int], str]:
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
            payload = update.message.text or update.message.caption or "<no-text>"
            return "message", user_id, payload

        if update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
            payload = update.callback_query.data or "<no-data>"
            return "callback", user_id, payload

        return "other", None, "<unknown-payload>"

    async def handle_webhook(self, request: web.Request) -> web.Response:
        request_id = self._build_request_id(request)
        has_secret_header = bool(request.headers.get("X-Telegram-Bot-Api-Secret-Token"))
        masked_path = mask_path(request.path)
        status_code = 200

        try:
            raw_body = await request.json()
        except Exception as e:
            log.error(
                "❌ Webhook JSON parse failed | request_id=%s path=%s has_secret_header=%s error=%s",
                request_id,
                masked_path,
                has_secret_header,
                e,
                exc_info=True,
            )
            log.info(
                "📨 Webhook POST | request_id=%s path=%s has_secret_header=%s status=%s",
                request_id,
                masked_path,
                has_secret_header,
                status_code,
            )
            return web.Response(status=status_code)

        updates_data: List[Dict[str, Any]] = raw_body if isinstance(raw_body, list) else [raw_body]

        log.info(
            "📨 Webhook POST | request_id=%s path=%s has_secret_header=%s updates=%s",
            request_id,
            masked_path,
            has_secret_header,
            len(updates_data),
        )

        for raw_update in updates_data:
            try:
                update = Update(**raw_update)
            except Exception as e:
                log.error(
                    "❌ Invalid update payload | request_id=%s path=%s error=%s payload=%s",
                    request_id,
                    masked_path,
                    e,
                    str(raw_update)[:500],
                    exc_info=True,
                )
                continue

            update_type, user_id, payload = self._extract_update_meta(update)

            log.info(
                "🔔 Update received | request_id=%s update_id=%s user_id=%s type=%s payload=%s",
                request_id,
                update.update_id,
                user_id,
                update_type,
                payload,
            )

            try:
                await self.dp.feed_webhook_update(bot=self.bot, update=update)
            except Exception as e:
                log.error(
                    "❌ Error processing update | request_id=%s update_id=%s user_id=%s type=%s error=%s",
                    request_id,
                    update.update_id,
                    user_id,
                    update_type,
                    e,
                    exc_info=True,
                )

        log.info(
            "✅ Webhook response | request_id=%s path=%s has_secret_header=%s status=%s",
            request_id,
            masked_path,
            has_secret_header,
            status_code,
        )

        return web.Response(status=status_code)


async def start_webhook_server(
    dp: Dispatcher,
    bot: Bot,
    host: str,
    port: int,
) -> Tuple[web.AppRunner, Dict[str, Any]]:
    base_url = _detect_base_url()
    
    # Generate or use provided secret
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN", "").strip() or _default_secret(bot.token)
    
    # Webhook path: if not explicitly set, use secret path for security
    path_env = os.getenv("TELEGRAM_WEBHOOK_PATH", "").strip()
    if path_env:
        path = path_env if path_env.startswith("/") else "/" + path_env
    else:
        # Default: secret path (not /webhook, but /webhook/<secret>)
        path = f"/webhook/{secret}"
    
    if not path.startswith("/"):
        path = "/" + path

    @web.middleware
    async def request_logger(request: web.Request, handler):
        """Log all incoming requests with timing and safe details."""
        start_time = time.time()
        remote_ip = request.headers.get("X-Forwarded-For", request.remote)
        
        try:
            response = await handler(request)
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log POST requests to webhook endpoints
            if request.method == "POST" and "/webhook" in request.path:
                content_length = request.headers.get("Content-Length", "?")
                log.info(
                    f"📨 Incoming webhook POST | "
                    f"path={mask_path(request.path)} "
                    f"status={response.status} "
                    f"size={content_length}b "
                    f"latency={latency_ms}ms "
                    f"ip={remote_ip}"
                )
            
            return response
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            log.error(
                f"❌ Request failed | "
                f"method={request.method} "
                f"path={mask_path(request.path)} "
                f"latency={latency_ms}ms "
                f"error={str(e)}"
            )
            raise

    @web.middleware
    async def secret_guard(request: web.Request, handler):
        """Dual security: secret path (primary) + header (fallback).
        
        Security model:
        1. If request path contains secret -> ALLOW (path-based auth)
        2. Else if request to /webhook and has valid header -> ALLOW (header-based auth)
        3. Else -> DENY (unauthorized)
        """
        # Only guard webhook endpoints
        if "/webhook" in request.path:
            # Check 1: Secret in path (primary security)
            if secret in request.path:
                # Valid secret path - allow
                return await handler(request)
            
            # Check 2: Legacy /webhook with valid header (fallback)
            provided_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if provided_header and provided_header == secret:
                # Valid header - allow
                return await handler(request)
            
            # Neither path nor header valid - deny
            client_ip = request.headers.get("X-Forwarded-For", request.remote)
            has_header = bool(request.headers.get("X-Telegram-Bot-Api-Secret-Token"))
            log.warning(
                f"🚫 Unauthorized webhook access | "
                f"ip={client_ip} "
                f"path={mask_path(request.path)} "
                f"has_header={has_header} "
                f"method={request.method}"
            )
            return web.Response(status=401, text="Unauthorized")
        
        return await handler(request)

    # Set max body size for uploads (10MB default, configurable)
    max_size = int(os.getenv("WEBHOOK_MAX_BODY_SIZE", 10 * 1024 * 1024))
    app = web.Application(
        middlewares=[request_logger, secret_guard],
        client_max_size=max_size
    )

    webhook_handler = DispatcherWebhookHandler(dp=dp, bot=bot)

    # Health endpoints
    async def healthz(request: web.Request) -> web.Response:
        """Liveness probe - always returns 200 OK quickly (no DB/external deps)."""
        import subprocess
        try:
            # Get git commit hash if available
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=1
            ).decode().strip()
        except Exception:
            commit = "unknown"
        
        return web.json_response({
            "ok": True,
            "version": os.getenv("APP_VERSION", "1.0.0"),
            "commit": commit,
            "time": time.time(),
        }, status=200)

    async def readyz(request: web.Request) -> web.Response:
        """Readiness probe - checks minimal dependencies with timeout."""
        import asyncio
        
        checks = {
            "bot_token": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "kie_key": bool(os.getenv("KIE_API_KEY")),
        }
        
        # Optional DB check with timeout
        db_ok = None
        try:
            from app.database.service import db_service
            if db_service and db_service.pool:
                # Quick DB ping with 1s timeout
                async with asyncio.timeout(1.0):
                    async with db_service.pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                        db_ok = True
        except asyncio.TimeoutError:
            db_ok = False
        except Exception:
            db_ok = False
        
        checks["db_ok"] = db_ok
        
        # Service is ready if bot_token and kie_key present
        # DB is optional (FREE models work without it)
        ready = checks["bot_token"] and checks["kie_key"]
        
        return web.json_response({
            "ready": ready,
            "checks": checks,
            "note": "DB is optional - FREE models work without it"
        }, status=200 if ready else 503)

    async def health(request: web.Request) -> web.Response:
        """Legacy health endpoint - returns current state."""
        return web.json_response(get_health_state())
    
    async def metrics_endpoint(request: web.Request) -> web.Response:
        """Metrics endpoint for monitoring - returns system metrics."""
        try:
            from app.utils.metrics import get_system_metrics
            from app.database.service import db_service
            
            metrics = await get_system_metrics(db_service)
            return web.json_response(metrics, status=200)
        except Exception as e:
            log.error(f"Failed to get metrics: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get("/", health)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/readyz", readyz)
    # Optional callback endpoint for Kie.ai. Some endpoints require callBackUrl
    # even if we also poll for results. Keeping it separate from the Telegram webhook
    # path avoids exposing the bot webhook secret.
    async def kie_callback(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            payload = None
        logger.info(
            "📩 Kie callback received | ip=%s size=%sb json=%s",
            request.remote,
            request.content_length or 0,
            isinstance(payload, dict),
        )
        # We don't rely on callbacks for the main flow (we poll), but we keep the endpoint
        # to satisfy providers that require it.
        return web.json_response({"ok": True})

    app.router.add_post("/kie/callback", kie_callback)
    app.router.add_get("/metrics", metrics_endpoint)
    
    # Webhook path probe (for manual testing - Telegram uses POST)
    async def webhook_probe(request: web.Request) -> web.Response:
        """Probe endpoint for webhook path (GET allowed for testing)."""
        return web.json_response({
            "ok": True,
            "path": mask_path(path),
            "method": request.method,
            "note": "Telegram sends POST requests to this path"
        })
    
    # Webhook path probe (GET).
    # IMPORTANT:
    # - Some aiohttp versions auto-register HEAD for GET.
    # - On Render, it is easy to accidentally set TELEGRAM_WEBHOOK_PATH="/" which already has GET/HEAD.
    # - Adding an explicit HEAD route can therefore crash the app on startup.
    #
    # We register only GET and NEVER register HEAD explicitly.
    # If aiohttp adds HEAD automatically -> great.
    # If not -> fine, we don't need a separate HEAD handler.
    try:
        # Prefer disabling implicit HEAD for GET when supported.
        # Even if HEAD exists elsewhere, we never add it explicitly here.
        app.router.add_get(path, webhook_probe, allow_head=False)
    except TypeError:
        # Old aiohttp: allow_head is not supported.
        # GET may auto-register HEAD; do not add HEAD separately.
        app.router.add_get(path, webhook_probe)
    except RuntimeError:
        # Path might already be occupied (misconfigured TELEGRAM_WEBHOOK_PATH like "/").
        # Probe endpoint is optional; never crash the app on startup.
        logger.warning("Webhook probe GET route already exists for path=%s (skipping)", mask_path(path))

    # Telegram webhook endpoint (aiogram handler with detailed logging)
    app.router.add_post(path, webhook_handler.handle_webhook)
    setup_application(app, dp, bot=bot)
    
    # ==== MEDIA PROXY ROUTE ====
    async def media_proxy(request: web.Request) -> web.Response:
        """Serve Telegram media files with signed URLs (security + expiration)."""
        file_id = request.match_info.get("file_id")
        sig_provided = request.query.get("sig", "")
        exp_provided = request.query.get("exp", "")
        
        # Verify signature includes expiration
        secret = os.getenv("MEDIA_PROXY_SECRET", "default_proxy_secret_change_me")
        payload = f"{file_id}:{exp_provided}"
        sig_expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        
        if sig_provided != sig_expected:
            # Don't log full URL (contains signature)
            remote_ip = request.headers.get("X-Forwarded-For", request.remote)
            log.info(f"Media proxy: Invalid signature | ip={remote_ip}")
            return web.Response(status=401, text="Unauthorized")
        
        # Check expiration
        try:
            exp_timestamp = int(exp_provided)
            if time.time() > exp_timestamp:
                log.info(f"Media proxy: Expired signature | file_id={file_id[:20]}...")
                return web.Response(status=401, text="Signature expired")
        except (ValueError, TypeError):
            log.warning(f"Media proxy: Invalid expiration format")
            return web.Response(status=401, text="Invalid signature")
        
        async def _stream_telegram_file(file_url: str) -> web.StreamResponse | web.Response:
            # Keep the bot token server-side (do not 302 redirect with token in URL)
            req_headers = {}
            if request.headers.get("Range"):
                req_headers["Range"] = request.headers["Range"]

            async with aiohttp.ClientSession() as session:
                async with session.get(file_url, headers=req_headers) as resp:
                    if resp.status not in (200, 206):
                        log.warning(f"Media proxy: Telegram fetch failed | status={resp.status}")
                        return web.Response(status=404, text="File not found")

                    headers: Dict[str, str] = {}
                    for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                        if h in resp.headers:
                            headers[h] = resp.headers[h]

                    stream = web.StreamResponse(status=resp.status, headers=headers)
                    await stream.prepare(request)
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        await stream.write(chunk)
                    await stream.write_eof()
                    return stream

        # Check cache
        global _media_proxy_cache
        now = datetime.now()
        
        if file_id in _media_proxy_cache:
            file_path, cached_at = _media_proxy_cache[file_id]
            if now - cached_at < _CACHE_TTL:
                file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
                return await _stream_telegram_file(file_url)
            else:
                # Cache expired
                del _media_proxy_cache[file_id]
        
        # Resolve file_path via Telegram API
        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            
            # Cache it
            _media_proxy_cache[file_id] = (file_path, now)
            
            # Redirect to Telegram CDN
            file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

            # Log without exposing tokens
            log.info(f"Media proxy: Resolved file_id (len={len(file_id)}) -> path")
            return await _stream_telegram_file(file_url)
        
        except Exception as e:
            log.warning(f"Media proxy: Failed to resolve file | error={type(e).__name__}")
            return web.Response(status=404, text="File not found")
    
    app.router.add_get("/media/telegram/{file_id}", media_proxy)

    runner = web.AppRunner(app, access_log=log)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()

    info: Dict[str, Any] = {
        "base_url": base_url,
        "path": path,
        "secret": "***" if secret else None,  # Don't log secret
        "webhook_url": (base_url.rstrip("/") + path) if base_url else None,
    }

    # Webhook self-check logging
    log.info("🔍 Webhook Configuration:")
    log.info(f"  Host: {host}:{port}")
    log.info(f"  Path: {mask_path(path)}")
    log.info(f"  Base URL: {base_url or 'NOT SET'}")
    log.info(f"  Full webhook URL: {(base_url.rstrip('/') + mask_path(path)) if base_url else 'MISSING'}")
    log.info(f"  Secret token: {'configured ✅' if secret else 'NOT SET ⚠️'}")
    log.info(f"  Security: path-based + header fallback")

    if not base_url:
        log.warning("⚠️⚠️⚠️ WEBHOOK_BASE_URL NOT SET ⚠️⚠️⚠️")
        log.warning("⚠️ Telegram will NOT deliver updates to this bot!")
        log.warning("⚠️ Set WEBHOOK_BASE_URL env var (e.g., https://your-app.onrender.com)")

    if base_url:
        # Retry webhook registration with exponential backoff
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(1, max_retries + 1):
            try:
                await bot.set_webhook(
                    url=info["webhook_url"],
                    secret_token=secret,
                    drop_pending_updates=False,
                )
                log.info("✅ Webhook registered successfully: %s", info["webhook_url"])
                
                # Startup diagnostics: Bot identity + Webhook health
                try:
                    me = await bot.get_me()
                    log.info(f"🤖 Bot identity: @{me.username} (id={me.id}, name={me.first_name})")
                    log.info(f"📱 You should test with: @{me.username}")
                except Exception as e:
                    log.error(f"❌ Failed to get bot identity: {e}")
                
                try:
                    webhook_info = await bot.get_webhook_info()
                    log.info("🔍 WebhookInfo:")
                    log.info(f"  - URL: {webhook_info.url}")
                    log.info(f"  - Pending updates: {webhook_info.pending_update_count}")
                    log.info(f"  - Max connections: {webhook_info.max_connections}")
                    log.info(f"  - IP address: {webhook_info.ip_address or 'N/A'}")
                    
                    if webhook_info.last_error_date:
                        from datetime import datetime
                        error_dt = datetime.fromtimestamp(webhook_info.last_error_date)
                        log.warning(f"⚠️ Last webhook error: {error_dt.isoformat()}")
                        log.warning(f"⚠️ Error message: {webhook_info.last_error_message}")
                    else:
                        log.info("  - No delivery errors ✅")
                except Exception as e:
                    log.error(f"❌ Failed to get webhook info: {e}")
                
                break
            except Exception as e:
                log.error(f"❌ Webhook registration failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    log.info(f"⏳ Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    log.critical("❌ Failed to register webhook after all retries")
                    # Keep server running for healthcheck and manual debugging
    else:
        log.warning(
            "⚠️ WEBHOOK_BASE_URL not set. Server running but Telegram won't deliver updates."
        )

    return runner, info


async def stop_webhook_server(runner: Optional[web.AppRunner]) -> None:
    if not runner:
        return
    try:
        # Graceful shutdown: clear in-memory caches
        global _media_proxy_cache
        _media_proxy_cache.clear()
        log.info("Cleared media proxy cache")
        
        # Clear idempotency and locks (if they're in-memory)
        try:
            from app.utils.idempotency import clear_all_keys
            clear_all_keys()
            log.info("Cleared idempotency keys")
        except (ImportError, AttributeError):
            pass
        
        try:
            from app.locking.job_lock import cleanup_all_locks
            cleanup_all_locks()
            log.info("Cleared all job locks")
        except (ImportError, AttributeError):
            pass
        
        await runner.cleanup()
        log.info("Webhook server stopped")
    except Exception:
        log.exception("Failed to stop webhook server")
