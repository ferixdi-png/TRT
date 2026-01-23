"""
Main application entry point with BOT_MODE logic.
PostgreSQL storage only.
"""
import os
import sys
import logging
import asyncio
import inspect
from typing import Optional

logger = logging.getLogger(__name__)

from app.utils.logging_config import setup_logging as setup_structured_logging
from app.utils.singleton_lock import is_lock_acquired, get_safe_mode
from app.storage import get_storage
from app.config_env import ConfigValidationError, normalize_webhook_base_url, validate_config
from app.diagnostics.boot import log_boot_report, run_boot_diagnostics


def get_bot_mode() -> str:
    """
    Get BOT_MODE from environment or determine automatically.
    
    Returns:
        "worker", "bot", "web", or "auto"
    """
    mode = os.getenv("BOT_MODE", "").lower()
    if mode in ("worker", "bot", "web", "auto"):
        return mode
    
    # AUTO mode: determine based on environment
    if os.getenv("TELEGRAM_BOT_TOKEN") and is_lock_acquired():
        return "bot"  # Will start polling
    elif os.getenv("PORT") and os.getenv("RENDER"):
        return "web"  # Healthcheck only
    else:
        return "auto"


async def initialize_storage() -> bool:
    """Initialize PostgreSQL storage."""
    storage = get_storage()
    if hasattr(storage, "initialize") and asyncio.iscoroutinefunction(storage.initialize):
        storage_ok = await storage.initialize()
        if storage_ok:
            logger.info("[STORAGE] db_initialized=true")
            return True
        logger.warning("[STORAGE] db_initialized=false")
    return False


async def start_telegram_bot():
    """Start Telegram bot polling."""
    from telegram.ext import Application
    from app.telegram_error_handler import ensure_error_handler_registered
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return
        
    if not is_lock_acquired():
        logger.info("[LOCK] Passive mode: telegram runner disabled")
        return
        
    try:
        app = Application.builder().token(token).build()
        ensure_error_handler_registered(app)
        
        # Register handlers
        # КРИТИЧНО: Исправляем импорт для Render
        try:
            # Пробуем импорт из корня (для main_render.py)
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent.absolute()
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from bot_kie import generation_handler
        except ImportError:
            try:
                # Fallback: пробуем из app.bot_kie (если есть)
                from app.bot_kie import generation_handler
            except ImportError:
                logger.error("Failed to import generation_handler from bot_kie or app.bot_kie")
                raise
        app.add_handler(generation_handler)
        
        # Delete webhook and start polling
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting Telegram bot polling...")
        if inspect.iscoroutinefunction(app.run_polling):
            await app.run_polling(drop_pending_updates=True)
        else:
            polling_result = app.run_polling(drop_pending_updates=True)
            if inspect.isawaitable(polling_result):
                await polling_result
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        raise


async def start_healthcheck_server(port: Optional[int] = None):
    """Start healthcheck HTTP server."""
    try:
        from aiohttp import web
        
        app_web = web.Application()
        
        async def healthcheck(request):
            safe_mode = get_safe_mode()
            lock_status = "acquired" if is_lock_acquired() else "not_acquired"
            return web.json_response({
                "status": "ok",
                "safe_mode": safe_mode,
                "lock_status": lock_status
            })
        
        app_web.router.add_get("/health", healthcheck)
        
        # NEVER hardcode ports - use PORT from environment (Render requirement)
        port_env = os.getenv("PORT", "10000").strip()
        try:
            port = port or int(port_env)
        except ValueError:
            logger.warning("Invalid PORT=%s, using default 10000", port_env)
            port = 10000
        logger.info(f"Starting healthcheck server on port {port}")
        
        runner = web.AppRunner(app_web)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Healthcheck server started on port {port}")
        
        # Keep server running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down healthcheck server...")
        finally:
            await runner.cleanup()
            
    except ImportError:
        logger.warning("aiohttp not available, skipping healthcheck server")
        # Fallback: use simple HTTP server
        try:
            import http.server
            import socketserver
            import threading
            
            class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/health":
                        safe_mode = get_safe_mode()
                        lock_status = "acquired" if is_lock_acquired() else "not_acquired"
                        response = f'{{"status":"ok","safe_mode":"{safe_mode}","lock_status":"{lock_status}"}}'
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(response.encode())
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def log_message(self, format, *args):
                    pass  # Suppress logs
            
            # NEVER hardcode ports - use PORT from environment (Render requirement)
            port_env = os.getenv("PORT", "10000").strip()
            try:
                port = port or int(port_env)
            except ValueError:
                logger.warning("Invalid PORT=%s, using default 10000", port_env)
                port = 10000
            httpd = socketserver.TCPServer(("0.0.0.0", port), HealthCheckHandler)
            logger.info(f"Starting simple healthcheck server on port {port}")
            
            def run_server():
                httpd.serve_forever()
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            logger.info("Simple healthcheck server started")
            
            # Keep process alive (fallback server runs in background thread)
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("Shutting down fallback healthcheck server...")
                httpd.shutdown()
        except Exception as e2:
            logger.error(f"Failed to start fallback healthcheck server: {e2}")
    except Exception as e:
        logger.error(f"Failed to start healthcheck server: {e}")


def _log_startup_summary(bot_mode: str) -> None:
    storage = get_storage()
    db_maxconn = getattr(storage, "max_pool_size", None) or int(os.getenv("DB_MAX_CONN", "5"))
    port_env = os.getenv("PORT", "10000").strip()
    try:
        port = int(port_env)
    except ValueError:
        port = 10000
    bot_instance_id = os.getenv("BOT_INSTANCE_ID", "").strip()
    webhook_base_url = normalize_webhook_base_url(os.getenv("WEBHOOK_BASE_URL", "").strip())
    redis_configured = bool(os.getenv("REDIS_URL", "").strip())
    token_status = "SET" if os.getenv("TELEGRAM_BOT_TOKEN") else "NOT_SET"
    kie_status = "SET" if os.getenv("KIE_API_KEY") else "NOT_SET"
    logger.info(
        "[STARTUP] storage_backend=db db_maxconn=%s port=%s mode=%s bot_instance_id=%s webhook_base_url=%s redis_configured=%s telegram_bot_token=%s kie_api_key=%s",
        db_maxconn,
        port,
        bot_mode,
        bot_instance_id or "missing",
        webhook_base_url or "missing",
        "yes" if redis_configured else "no",
        token_status,
        kie_status,
    )


async def main():
    """Main application entry point."""
    setup_structured_logging()
    
    logger.info("Starting application...")
    try:
        validate_config(strict=True)
    except ConfigValidationError as exc:
        logger.error("CONFIG_VALIDATION_FAILED missing=%s invalid=%s", exc.missing, exc.invalid)
        sys.exit(1)
    report = await run_boot_diagnostics(os.environ, storage=None, redis_client=None)
    log_boot_report(report)
    if report.get("result") == "FAIL":
        logger.error("BOOT DIAGNOSTICS failed, aborting startup.")
        sys.exit(1)
    
    # Initialize storage
    await initialize_storage()
    
    # Determine bot mode
    bot_mode = get_bot_mode()
    logger.info(f"BOT_MODE: {bot_mode}, Safe mode: {get_safe_mode()}")
    _log_startup_summary(bot_mode)
    
    # Start services based on mode
    try:
        if bot_mode in ("worker", "bot") or (bot_mode == "auto" and is_lock_acquired()):
            if is_lock_acquired():
                # Start Telegram bot (runs indefinitely)
                await start_telegram_bot()
            else:
                logger.info("[LOCK] Passive mode: telegram runner disabled")
                # Start healthcheck only (runs indefinitely)
                await start_healthcheck_server()
        elif bot_mode == "web" or (os.getenv("PORT") and not is_lock_acquired()):
            # Web/healthcheck only mode (runs indefinitely)
            await start_healthcheck_server()
        else:
            logger.warning("No services to start. Set BOT_MODE, PORT, or TELEGRAM_BOT_TOKEN")
            # Keep process alive even if nothing started
            await start_healthcheck_server()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)
