"""
Main application entry point with BOT_MODE logic and singleton lock handling.
"""
import os
import sys
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

from app.locking.single_instance import SingletonLock
from app.utils.singleton_lock import is_lock_acquired, get_safe_mode
from app.storage.pg_storage import PGStorage, async_check_pg


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


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
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        logger.info("DATABASE_URL not set, skipping storage initialization")
        return False
        
    # Use async_check_pg (no nested event loop)
    if not await async_check_pg(dsn):
        logger.error("PostgreSQL connection test failed")
        return False
        
    storage = PGStorage(dsn)
    if await storage.initialize():
        logger.info("PostgreSQL storage initialized")
        return True
    return False


async def start_telegram_bot():
    """Start Telegram bot polling."""
    from telegram.ext import Application
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping bot startup")
        return
        
    if not is_lock_acquired():
        logger.info("[LOCK] Passive mode: telegram runner disabled")
        return
        
    try:
        app = Application.builder().token(token).build()
        
        # Register handlers
        try:
            from app.bot_kie import generation_handler
        except ImportError:
            from bot_kie import generation_handler
        app.add_handler(generation_handler)
        
        # Delete webhook and start polling
        await app.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting Telegram bot polling...")
        await app.run_polling(drop_pending_updates=True)
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
        port_env = os.getenv("PORT")
        if not port_env:
            logger.warning("PORT not set, cannot start healthcheck server")
            return
        port = port or int(port_env)
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
            port_env = os.getenv("PORT")
            if not port_env:
                logger.warning("PORT not set, cannot start fallback healthcheck server")
                return
            port = port or int(port_env)
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


async def main():
    """Main application entry point."""
    setup_logging()
    
    logger.info("Starting application...")
    
    # Initialize storage
    await initialize_storage()
    
    # Acquire singleton lock
    lock = SingletonLock()
    lock_acquired = await lock.acquire()
    
    if not lock_acquired and not is_lock_acquired():
        logger.info("[LOCK] Passive mode: lock not acquired, running in safe mode")
    
    # Determine bot mode
    bot_mode = get_bot_mode()
    logger.info(f"BOT_MODE: {bot_mode}, Safe mode: {get_safe_mode()}")
    
    # Start services based on mode
    try:
        if bot_mode in ("worker", "bot") or (bot_mode == "auto" and is_lock_acquired()):
            if is_lock_acquired():
                # Start Telegram bot (runs indefinitely)
                await start_telegram_bot()
            else:
                logger.info("[LOCK] Passive mode: telegram runner disabled")
                # Start healthcheck only (runs indefinitely)
                if os.getenv("PORT"):
                    await start_healthcheck_server()
                else:
                    # No PORT, just wait to keep process alive
                    logger.info("[LOCK] Passive mode: keeping process alive (no PORT set)")
                    await asyncio.Event().wait()
        elif bot_mode == "web" or (os.getenv("PORT") and not is_lock_acquired()):
            # Web/healthcheck only mode (runs indefinitely)
            await start_healthcheck_server()
        else:
            logger.warning("No services to start. Set BOT_MODE, PORT, or TELEGRAM_BOT_TOKEN")
            # Keep process alive even if nothing started
            if os.getenv("PORT"):
                await start_healthcheck_server()
            else:
                await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        # Release lock on shutdown
        await lock.release()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)


