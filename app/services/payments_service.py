"""
Payments service - работа с платежами и курсами валют
БЕЗ зависимостей от bot_kie.py
"""

import logging
from typing import Optional
from app.storage import get_storage
from app.config import get_settings

logger = logging.getLogger(__name__)


# Константы для конвертации
CREDIT_TO_USD = 0.005  # 1 credit = $0.005
def get_usd_to_rub_rate() -> float:
    """
    Получить курс USD к RUB
    Пока возвращает дефолтное значение, можно расширить для чтения из storage
    """
    settings = get_settings()
    return getattr(settings, "usd_to_rub", 77.83)


def set_usd_to_rub_rate(rate: float) -> None:
    """
    Установить курс USD к RUB
    Пока заглушка, можно расширить для сохранения в storage
    """
    logger.warning("USD to RUB rate is locked from pricing config; ignored update: %s", rate)


def credit_to_rub(credits: float) -> float:
    """Конвертировать кредиты в рубли"""
    return credits * CREDIT_TO_USD * get_usd_to_rub_rate()


def rub_to_credit(rub: float) -> float:
    """Конвертировать рубли в кредиты"""
    return rub / (CREDIT_TO_USD * get_usd_to_rub_rate())
