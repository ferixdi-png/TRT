#!/usr/bin/env python3
"""
Render-first entrypoint ╨┤╨╗╤П Telegram Bot
╨Х╨┤╨╕╨╜╨░╤П ╤В╨╛╤З╨║╨░ ╨▓╤Е╨╛╨┤╨░ ╨┤╨╗╤П ╨╖╨░╨┐╤Г╤Б╨║╨░ ╨╜╨░ Render.com (Web Service ╨╕╨╗╨╕ Worker)
"""

import sys
import os
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional

# ╨Ф╨╛╨▒╨░╨▓╨╗╤П╨╡╨╝ ╨║╨╛╤А╨╜╨╡╨▓╤Г╤О ╨┤╨╕╤А╨╡╨║╤В╨╛╤А╨╕╤О ╨▓ ╨┐╤Г╤В╤М (╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю ╨┤╨╗╤П Render)
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# ╨Э╨░╤Б╤В╤А╨░╨╕╨▓╨░╨╡╨╝ ╨╗╨╛╨│╨╕╤А╨╛╨▓╨░╨╜╨╕╨╡ ╨Я╨Х╨а╨Х╨Ф ╨╕╨╝╨┐╨╛╤А╤В╨╛╨╝ ╨┤╤А╤Г╨│╨╕╤Е ╨╝╨╛╨┤╤Г╨╗╨╡╨╣
from app.utils.logging_config import setup_logging, get_logger

setup_logging(level=logging.INFO)
logger = get_logger(__name__)

# ╨У╨╗╨╛╨▒╨░╨╗╤М╨╜╤Л╨╡ ╨┐╨╡╤А╨╡╨╝╨╡╨╜╨╜╤Л╨╡
_start_time = time.time()
_application: Optional[object] = None


def log_env_snapshot():
    """╨Ы╨╛╨│╨╕╤А╤Г╨╡╤В snapshot ENV ╨┐╨╡╤А╨╡╨╝╨╡╨╜╨╜╤Л╤Е ╨▒╨╡╨╖ ╤Б╨╡╨║╤А╨╡╤В╨╛╨▓"""
    env_vars = {
        "PORT": os.getenv("PORT", "not set"),
        "RENDER": os.getenv("RENDER", "not set"),
        "ENV": os.getenv("ENV", "not set"),
        "BOT_MODE": os.getenv("BOT_MODE", "not set"),
        "STORAGE_MODE": os.getenv("STORAGE_MODE", "not set"),
        "DATABASE_URL": "[SET]" if os.getenv("DATABASE_URL") else "[NOT SET]",
        "TELEGRAM_BOT_TOKEN": "[SET]" if os.getenv("TELEGRAM_BOT_TOKEN") else "[NOT SET]",
        "KIE_API_KEY": "[SET]" if os.getenv("KIE_API_KEY") else "[NOT SET]",
        "KIE_API_URL": os.getenv("KIE_API_URL", "not set"),
        "TEST_MODE": os.getenv("TEST_MODE", "not set"),
        "DRY_RUN": os.getenv("DRY_RUN", "not set"),
        "ALLOW_REAL_GENERATION": os.getenv("ALLOW_REAL_GENERATION", "not set"),
    }
    
    logger.info("=" * 60)
    logger.info("ENVIRONMENT VARIABLES SNAPSHOT")
    logger.info("=" * 60)
    for key, value in sorted(env_vars.items()):
        logger.info(f"{key}={value}")
    logger.info("=" * 60)


def ensure_data_directory(data_dir: str) -> bool:
    """╨У╨░╤А╨░╨╜╤В╨╕╤А╤Г╨╡╤В ╤Б╨╛╨╖╨┤╨░╨╜╨╕╨╡ data ╨┤╨╕╤А╨╡╨║╤В╨╛╤А╨╕╨╕ ╨╕ ╨┐╤А╨╛╨▓╨╡╤А╤П╨╡╤В ╨┐╤А╨░╨▓╨░ ╨╖╨░╨┐╨╕╤Б╨╕"""
    try:
        data_path = Path(data_dir)
        data_path.mkdir(parents=True, exist_ok=True)
        
        # ╨Я╤А╨╛╨▓╨╡╤А╤П╨╡╨╝ ╨┐╤А╨░╨▓╨░ ╨╖╨░╨┐╨╕╤Б╨╕
        test_file = data_path / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            logger.info(f"[OK] Data directory writable: {data_dir}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] Cannot write to data directory {data_dir}: {e}")
            return False
    except Exception as e:
        logger.error(f"[FAIL] Cannot create data directory {data_dir}: {e}")
        return False


def load_and_validate_settings():
    """╨Ч╨░╨│╤А╤Г╨╢╨░╨╡╤В ╨╕ ╨▓╨░╨╗╨╕╨┤╨╕╤А╤Г╨╡╤В ╨╜╨░╤Б╤В╤А╨╛╨╣╨║╨╕ ╨╕╨╖ ENV"""
    from app.config import get_settings
    
    logger.info("=" * 60)
    logger.info("BOT STARTING")
    logger.info("=" * 60)
    
    try:
        # ╨Ы╨╛╨│╨╕╤А╤Г╨╡╨╝ ENV snapshot
        log_env_snapshot()
        
        # ╨Ч╨░╨│╤А╤Г╨╢╨░╨╡╨╝ ╨╜╨░╤Б╤В╤А╨╛╨╣╨║╨╕ ╤Б ╨▓╨░╨╗╨╕╨┤╨░╤Ж╨╕╨╡╨╣
        settings = get_settings(validate=True)
        
        # Startup banner
        logger.info("=" * 60)
        logger.info("STARTUP BANNER")
        logger.info("=" * 60)
        logger.info(f"Python version: {sys.version.split()[0]}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Process ID: {os.getpid()}")
        logger.info(f"Render environment: {os.getenv('RENDER', 'not detected')}")
        logger.info(f"Storage mode: {settings.get_storage_mode()}")
        logger.info(f"KIE mode: {'stub' if os.getenv('KIE_STUB') else ('real' if settings.kie_api_key else 'disabled')}")
        logger.info(f"Bot mode: {settings.bot_mode}")
        logger.info(f"Port: {settings.port if settings.port > 0 else 'disabled (Worker mode)'}")
        logger.info(f"Data directory: {settings.data_dir}")
        logger.info("=" * 60)
        
        # ╨Я╤А╨╛╨▓╨╡╤А╤П╨╡╨╝ data directory
        if not ensure_data_directory(settings.data_dir):
            logger.error("[FAIL] Data directory not writable, exiting")
            sys.exit(1)
        
        return settings
    except ValueError as e:
        logger.error("=" * 60)
        logger.error("CONFIGURATION VALIDATION FAILED")
        logger.error("=" * 60)
        logger.error(str(e))
        logger.error("=" * 60)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace
        log_error_with_stacktrace(logger, e, "Failed to load settings")
        sys.exit(1)


async def build_application(settings):
    """╨б╨╛╨╖╨┤╨░╨╡╤В ╨╕ ╨╜╨░╤Б╤В╤А╨░╨╕╨▓╨░╨╡╤В Telegram Application"""
    global _application
    
    try:
        # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨Ш╨╝╨┐╨╛╤А╤В bot_kie ╤Б ╤П╨▓╨╜╤Л╨╝ ╤Г╨║╨░╨╖╨░╨╜╨╕╨╡╨╝ ╨┐╤Г╤В╨╕
        create_bot_application = None
        try:
            from bot_kie import create_bot_application
        except ImportError as e1:
            logger.warning(f"[BUILD] Failed to import from bot_kie: {e1}, trying app.bot_kie")
            try:
                # ╨Я╤А╨╛╨▒╤Г╨╡╨╝ ╨╕╨╝╨┐╨╛╤А╤В ╨╕╨╖ app.bot_kie (╨╡╤Б╨╗╨╕ ╤В╨░╨╝ ╨╡╤Б╤В╤М ╤Д╤Г╨╜╨║╤Ж╨╕╤П)
                from app.bootstrap import create_application as create_bot_application
                logger.info("[BUILD] Using app.bootstrap.create_application")
            except ImportError as e2:
                logger.error(f"[BUILD] Failed to import from app.bootstrap: {e2}")
                logger.error(f"[BUILD] sys.path: {sys.path}")
                logger.error(f"[BUILD] Current dir: {os.getcwd()}")
                logger.error(f"[BUILD] Script dir: {Path(__file__).parent}")
                # ╨Я╤А╨╛╨▒╤Г╨╡╨╝ ╨┤╨╛╨▒╨░╨▓╨╕╤В╤М ╨┐╤Г╤В╤М ╤П╨▓╨╜╨╛
                bot_kie_path = Path(__file__).parent / "bot_kie.py"
                if bot_kie_path.exists():
                    logger.info(f"[BUILD] bot_kie.py exists at {bot_kie_path}")
                    # ╨Я╤А╨╛╨▒╤Г╨╡╨╝ ╨┐╤А╤П╨╝╨╛╨╣ ╨╕╨╝╨┐╨╛╤А╤В ╤З╨╡╤А╨╡╨╖ importlib
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("bot_kie", bot_kie_path)
                    if spec and spec.loader:
                        bot_kie_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(bot_kie_module)
                        create_bot_application = getattr(bot_kie_module, "create_bot_application", None)
                        if create_bot_application:
                            logger.info("[BUILD] Successfully loaded create_bot_application via importlib")
                else:
                    logger.error(f"[BUILD] bot_kie.py NOT found at {bot_kie_path}")
                if not create_bot_application:
                    raise ImportError(f"Could not import create_bot_application: {e1}, {e2}")
        
        if not create_bot_application:
            raise ImportError("create_bot_application is None after import attempts")
        
        logger.info("[BUILD] Creating Telegram Application...")
        _application = await create_bot_application(settings)
        logger.info("[BUILD] Application created successfully")
        
        return _application
    except (AttributeError, NameError) as e:
        logger.warning(f"[BUILD] create_bot_application not found: {e}, using legacy initialization")
        return None
    except ImportError as e:
        logger.error(f"[BUILD] Import error: {e}")
        logger.warning("[BUILD] Using legacy bot_kie.main() initialization")
        return None
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace
        log_error_with_stacktrace(logger, e, "Failed to build application")
        raise


async def start_health_server(port: int) -> bool:
    """╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╤В healthcheck ╤Б╨╡╤А╨▓╨╡╤А ╨▓ ╤В╨╛╨╝ ╨╢╨╡ event loop"""
    if port == 0:
        logger.info("[HEALTH] PORT not set, skipping healthcheck server (Worker mode)")
        return False
    
    try:
        from app.utils.healthcheck import start_health_server
        return await start_health_server(port=port)
    except Exception as e:
        logger.warning(f"[HEALTH] Failed to start health server: {e}")
        return False


async def run(settings, application):
    """╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╤В ╨▒╨╛╤В╨░ (polling ╨╕╨╗╨╕ webhook)"""
    global _application
    
    # Singleton lock ╨┤╨╛╨╗╨╢╨╡╨╜ ╨▒╤Л╤В╤М ╨┐╨╛╨╗╤Г╤З╨╡╨╜ ╨Ф╨Ю ╨╗╤О╨▒╤Л╤Е async ╨╛╨┐╨╡╤А╨░╤Ж╨╕╨╣
    from app.utils.singleton_lock import acquire_singleton_lock, release_singleton_lock
    
    if not acquire_singleton_lock():
        # acquire_singleton_lock ╤Г╨╢╨╡ ╨▓╤Л╨╖╨▓╨░╨╗ exit(0) ╨╡╤Б╨╗╨╕ lock ╨╜╨╡ ╨┐╨╛╨╗╤Г╤З╨╡╨╜
        return
    
    try:
        # ╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ healthcheck ╤Б╨╡╤А╨▓╨╡╤А (╨╡╤Б╨╗╨╕ PORT ╨╖╨░╨┤╨░╨╜ - Web Service ╤А╨╡╨╢╨╕╨╝)
        if settings.port > 0:
            logger.info(f"[HEALTH] Starting healthcheck server on port {settings.port} (Web Service mode)")
            await start_health_server(port=settings.port)
        else:
            logger.info("[HEALTH] Port not set, running in Worker mode (no healthcheck)")
        
        if application is None:
            # ╨Ш╤Б╨┐╨╛╨╗╤М╨╖╤Г╨╡╨╝ ╤Б╤В╨░╤А╤Л╨╣ ╤Б╨┐╨╛╤Б╨╛╨▒ ╤З╨╡╤А╨╡╨╖ bot_kie.main()
            logger.info("[RUN] Using legacy bot_kie.main() initialization")
            try:
                from bot_kie import main as bot_main
                await bot_main()
            except ImportError as e:
                logger.error(f"[RUN] Failed to import bot_kie.main: {e}")
                logger.error("[RUN] Falling back to app.main")
                from app.main import main as app_main
                await app_main()
        else:
            # ╨Ш╤Б╨┐╨╛╨╗╤М╨╖╤Г╨╡╨╝ ╨╜╨╛╨▓╤Л╨╣ ╤Б╨┐╨╛╤Б╨╛╨▒
            logger.info("[RUN] Initializing application...")
            await application.initialize()
            await application.start()
            
            logger.info("=" * 60)
            logger.info("BOT READY")
            logger.info("=" * 60)
            logger.info("Handlers registered and application started")
            
            # ╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ polling ╨╕╨╗╨╕ webhook
            if settings.bot_mode == "webhook":
                if not settings.webhook_url:
                    logger.error("[FAIL] WEBHOOK_URL not set for webhook mode")
                    sys.exit(1)
                await application.bot.set_webhook(settings.webhook_url)
                logger.info(f"[RUN] Webhook set to {settings.webhook_url}")
                logger.info("[RUN] Webhook mode - bot is ready")
            else:
                # Polling mode - ╨▒╨╡╨╖╨╛╨┐╨░╤Б╨╜╤Л╨╣ ╨╖╨░╨┐╤Г╤Б╨║ ╤Б ╨╛╨▒╤А╨░╨▒╨╛╤В╨║╨╛╨╣ ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В╨╛╨▓
                logger.info("[RUN] Starting polling...")
                
                # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨Ч╨░╨┤╨╡╤А╨╢╨║╨░ ╨┐╨╡╤А╨╡╨┤ ╨╖╨░╨┐╤Г╤Б╨║╨╛╨╝ polling ╨┤╨╗╤П ╨┐╤А╨╡╨┤╨╛╤В╨▓╤А╨░╤Й╨╡╨╜╨╕╤П ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В╨╛╨▓
                logger.info("[RUN] Waiting 15 seconds to avoid conflicts with previous instance...")
                await asyncio.sleep(15)
                
                # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨г╨┤╨░╨╗╤П╨╡╨╝ webhook ╨Я╨Х╨а╨Х╨Ф ╨╖╨░╨┐╤Г╤Б╨║╨╛╨╝ polling
                try:
                    await application.bot.delete_webhook(drop_pending_updates=True)
                    webhook_info = await application.bot.get_webhook_info()
                    if webhook_info.url:
                        logger.warning(f"[RUN] Webhook still present: {webhook_info.url}")
                    else:
                        logger.info("[RUN] Webhook removed successfully")
                except Exception as e:
                    logger.warning(f"[RUN] Error removing webhook: {e}")
                    # ╨Я╤А╨╛╨▓╨╡╤А╤П╨╡╨╝ ╨╜╨░ ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В
                    from telegram.error import Conflict
                    if isinstance(e, Conflict) or "Conflict" in str(e) or "409" in str(e):
                        logger.error("[RUN] Conflict detected while removing webhook - exiting")
                        from app.bot_mode import handle_conflict_gracefully
                        handle_conflict_gracefully(e if isinstance(e, Conflict) else Conflict(str(e)), "polling")
                        return
                
                # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨Ф╨╛╨▒╨░╨▓╨╗╤П╨╡╨╝ ╨╛╨▒╤А╨░╨▒╨╛╤В╤З╨╕╨║ ╨╛╤И╨╕╨▒╨╛╨║ ╨┤╨╗╤П updater
                async def handle_updater_error(update, context):
                    """╨Ю╨▒╤А╨░╨▒╨╛╤В╤З╨╕╨║ ╨╛╤И╨╕╨▒╨╛╨║ ╨┤╨╗╤П updater polling loop"""
                    error = context.error
                    error_msg = str(error) if error else ""
                    
                    from telegram.error import Conflict
                    if isinstance(error, Conflict) or "Conflict" in error_msg or "terminated by other getUpdates" in error_msg or "409" in error_msg:
                        logger.error(f"[UPDATER] 409 CONFLICT in updater loop: {error_msg}")
                        logger.error("[UPDATER] Stopping updater and exiting...")
                        
                        # ╨Ю╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ updater ╨╜╨╡╨╝╨╡╨┤╨╗╨╡╨╜╨╜╨╛
                        try:
                            if application.updater and application.updater.running:
                                await application.updater.stop()
                                logger.info("[UPDATER] Updater stopped")
                        except Exception as e:
                            logger.warning(f"[UPDATER] Error stopping updater: {e}")
                        
                        # ╨Ю╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ application
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass
                        
                        # ╨Ю╤Б╨▓╨╛╨▒╨╛╨╢╨┤╨░╨╡╨╝ lock ╨╕ ╨▓╤Л╤Е╨╛╨┤╨╕╨╝
                        try:
                            from app.locking.single_instance import release_single_instance_lock
                            release_single_instance_lock()
                        except:
                            pass
                        
                        from app.bot_mode import handle_conflict_gracefully
                        handle_conflict_gracefully(error if isinstance(error, Conflict) else Conflict(error_msg), "polling")
                        import os
                        os._exit(0)
                
                # ╨Ф╨╛╨▒╨░╨▓╨╗╤П╨╡╨╝ ╨╛╨▒╤А╨░╨▒╨╛╤В╤З╨╕╨║ ╨╛╤И╨╕╨▒╨╛╨║ ╨┤╨╗╤П updater
                application.add_error_handler(handle_updater_error)
                
                # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨Я╤А╨╛╨▓╨╡╤А╤П╨╡╨╝ ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В ╨Я╨Х╨а╨Х╨Ф ╨╖╨░╨┐╤Г╤Б╨║╨╛╨╝ polling
                logger.info("[RUN] Checking for conflicts before polling start...")
                try:
                    # ╨Я╤Л╤В╨░╨╡╨╝╤Б╤П ╤Б╨┤╨╡╨╗╨░╤В╤М ╤В╨╡╤Б╤В╨╛╨▓╤Л╨╣ getUpdates ╨┤╨╗╤П ╨┐╤А╨╛╨▓╨╡╤А╨║╨╕ ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В╨░
                    test_updates = await application.bot.get_updates(limit=1, timeout=1)
                    logger.info("[RUN] Pre-flight check passed: no conflicts detected")
                except Exception as test_e:
                    from telegram.error import Conflict
                    error_msg = str(test_e)
                    if isinstance(test_e, Conflict) or "Conflict" in error_msg or "409" in error_msg or "terminated by other getUpdates" in error_msg:
                        logger.error(f"[RUN] тЭМтЭМтЭМ CONFLICT DETECTED in pre-flight check: {error_msg}")
                        logger.error("[RUN] Another bot instance is already polling - exiting")
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass
                        from app.bot_mode import handle_conflict_gracefully
                        handle_conflict_gracefully(test_e if isinstance(test_e, Conflict) else Conflict(error_msg), "polling")
                        return
                    else:
                        logger.warning(f"[RUN] Pre-flight check warning (non-conflict): {test_e}")
                
                # ╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю: ╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ polling ╤Б ╨╛╨▒╤А╨░╨▒╨╛╤В╨║╨╛╨╣ ╨║╨╛╨╜╤Д╨╗╨╕╨║╤В╨╛╨▓
                try:
                    await application.updater.start_polling(drop_pending_updates=True)
                    logger.info("[RUN] Polling started successfully")
                except Exception as e:
                    from telegram.error import Conflict
                    error_msg = str(e)
                    if isinstance(e, Conflict) or "Conflict" in error_msg or "409" in error_msg or "terminated by other getUpdates" in error_msg:
                        logger.error(f"[RUN] тЭМтЭМтЭМ CONFLICT DETECTED during polling start: {error_msg}")
                        logger.error("[RUN] Stopping updater and exiting immediately...")
                        
                        # ╨Ю╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ updater ╨╜╨╡╨╝╨╡╨┤╨╗╨╡╨╜╨╜╨╛
                        try:
                            if application.updater and application.updater.running:
                                await application.updater.stop()
                                logger.info("[RUN] Updater stopped")
                        except Exception as stop_e:
                            logger.warning(f"[RUN] Error stopping updater: {stop_e}")
                        
                        # ╨Ю╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ application
                        try:
                            await application.stop()
                            await application.shutdown()
                        except:
                            pass
                        
                        # ╨Ю╤Б╨▓╨╛╨▒╨╛╨╢╨┤╨░╨╡╨╝ lock
                        try:
                            from app.locking.single_instance import release_single_instance_lock
                            release_single_instance_lock()
                        except:
                            pass
                        
                        from app.bot_mode import handle_conflict_gracefully
                        handle_conflict_gracefully(e if isinstance(e, Conflict) else Conflict(error_msg), "polling")
                        import os
                        os._exit(0)  # ╨Э╨╡╨╝╨╡╨┤╨╗╨╡╨╜╨╜╤Л╨╣ ╨▓╤Л╤Е╨╛╨┤
                    else:
                        raise  # Re-raise non-Conflict errors
            
            # ╨Ц╨┤╨╡╨╝ ╨╛╤Б╤В╨░╨╜╨╛╨▓╨║╨╕
            try:
                await asyncio.Event().wait()  # ╨Ц╨┤╨╡╨╝ ╨▒╨╡╤Б╨║╨╛╨╜╨╡╤З╨╜╨╛
            except KeyboardInterrupt:
                logger.info("[STOP] Bot stopped by user")
            finally:
                await application.stop()
                await application.shutdown()
    except KeyboardInterrupt:
        logger.info("[STOP] Bot stopped by user")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace
        log_error_with_stacktrace(logger, e, "Fatal error during bot run")
        logger.error("[FAIL] Bot failed to run. Check logs above for details.")
        sys.exit(1)
    finally:
        # ╨Ю╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╡╨╝ healthcheck ╤Б╨╡╤А╨▓╨╡╤А
        from app.utils.healthcheck import stop_health_server
        await stop_health_server()
        
        # ╨Ю╤Б╨▓╨╛╨▒╨╛╨╢╨┤╨░╨╡╨╝ singleton lock
        release_singleton_lock()


async def main():
    """╨У╨╗╨░╨▓╨╜╨░╤П async ╤Д╤Г╨╜╨║╤Ж╨╕╤П"""
    try:
        # 1. ╨Ч╨░╨│╤А╤Г╨╢╨░╨╡╨╝ ╨╕ ╨▓╨░╨╗╨╕╨┤╨╕╤А╤Г╨╡╨╝ ╨╜╨░╤Б╤В╤А╨╛╨╣╨║╨╕
        settings = load_and_validate_settings()
        
        # 2. ╨б╨╛╨╖╨┤╨░╨╡╨╝ application
        application = await build_application(settings)
        
        # 3. ╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ ╨▒╨╛╤В╨░
        await run(settings, application)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace
        log_error_with_stacktrace(logger, e, "Fatal error in main")
        sys.exit(1)


if __name__ == "__main__":
    # ╨Ч╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ async main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[STOP] Bot stopped by user")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        from app.utils.logging_config import log_error_with_stacktrace
        log_error_with_stacktrace(logger, e, "Fatal error in asyncio.run")
        sys.exit(1)

