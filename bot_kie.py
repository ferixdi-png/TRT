    from app.config import get_settings
    from app.utils.webhook import build_webhook_url, get_webhook_base_url, get_webhook_secret_path

    settings = get_settings(validate=False)
    BOT_TOKEN = settings.telegram_bot_token
    CONFIG_DATABASE_URL = settings.database_url
    BOT_MODE = settings.bot_mode
    WEBHOOK_BASE_URL = settings.webhook_base_url
    WEBHOOK_URL = settings.webhook_url
    from app.utils.webhook import build_webhook_url, get_webhook_base_url, get_webhook_secret_path
    WEBHOOK_BASE_URL = get_webhook_base_url()
    WEBHOOK_URL = build_webhook_url(WEBHOOK_BASE_URL, get_webhook_secret_path(BOT_TOKEN or ""))
            if os.getenv("PORT") and get_webhook_base_url():
        webhook_base_url = WEBHOOK_BASE_URL or get_webhook_base_url()
        webhook_url = WEBHOOK_URL or build_webhook_url(
            webhook_base_url,
            get_webhook_secret_path(BOT_TOKEN or "")
        )
            logger.error("❌ WEBHOOK_BASE_URL not set for webhook mode!")
            logger.error("   Set WEBHOOK_BASE_URL environment variable or use BOT_MODE=polling")
