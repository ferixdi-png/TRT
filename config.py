"""
DEPRECATED: Этот модуль существует только для обратной совместимости.
Используйте app.config.get_settings() вместо этого.

Thin wrapper вокруг app.config для обратной совместимости.
"""

# Импортируем из app.config
from app.config import get_settings, Settings as AppSettings

# Получаем настройки
_app_settings = None

def _get_app_settings():
    """Ленивая инициализация настроек"""
    global _app_settings
    if _app_settings is None:
        _app_settings = get_settings()
    return _app_settings

# Создаем объект для обратной совместимости
class Settings:
    """Deprecated: используйте app.config.Settings"""
    
    def __init__(self):
        s = _get_app_settings()
        self.BOT_TOKEN = s.telegram_bot_token
        self.ADMIN_ID = s.admin_id
        self.PAYMENT_PHONE = s.payment_phone
        self.PAYMENT_BANK = s.payment_bank
        self.PAYMENT_CARD_HOLDER = s.payment_card_holder
        self.SUPPORT_TELEGRAM = s.support_telegram
        self.SUPPORT_TEXT = s.support_text
        
        # Константы (не из ENV)
        self.CREDIT_TO_USD = 0.005
        self.USD_TO_RUB = 77.2222
        self.FREE_GENERATIONS_PER_DAY = 5
        self.REFERRAL_BONUS_GENERATIONS = 5
        self.FREE_MODEL_ID = "z-image"
        
        # File paths
        self.BALANCES_FILE = "user_balances.json"
        self.USER_LANGUAGES_FILE = "user_languages.json"
        self.GIFT_CLAIMED_FILE = "gift_claimed.json"
        self.ADMIN_LIMITS_FILE = "admin_limits.json"
        self.PAYMENTS_FILE = "payments.json"
        self.BLOCKED_USERS_FILE = "blocked_users.json"
        self.FREE_GENERATIONS_FILE = "daily_free_generations.json"
        self.PROMOCODES_FILE = "promocodes.json"
        self.REFERRALS_FILE = "referrals.json"
        self.BROADCASTS_FILE = "broadcasts.json"
        self.GENERATIONS_HISTORY_FILE = "generations_history.json"
    
    def validate(self):
        """Валидация настроек"""
        s = _get_app_settings()
        s.validate()
        return True

# Глобальный экземпляр для обратной совместимости
settings = Settings()



