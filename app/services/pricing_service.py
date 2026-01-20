"""
Сервис расчёта цен для моделей KIE AI.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict
from app.config import Settings
from app.kie_catalog.catalog import get_model, ModelSpec
from app.pricing.ssot_catalog import get_min_price_rub

logger = logging.getLogger(__name__)


def get_usd_to_rub(settings: Settings) -> float:
    """
    Получает курс USD к RUB из настроек.
    
    Args:
        settings: Настройки приложения
    
    Returns:
        Курс USD к RUB (по умолчанию 100.0)
    """
    return getattr(settings, 'usd_to_rub', 77.83)


def _quantize_decimal(value: Decimal, places: int) -> Decimal:
    quant = Decimal("1").scaleb(-places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def user_price_rub(
    official_usd: float,
    usd_to_rub: float,
    price_multiplier: float = 2.0,
    *,
    is_admin: bool = False,
) -> int:
    """
    Рассчитывает цену для пользователя в рублях.
    
    Формула: official_usd * usd_to_rub * price_multiplier
    
    Args:
        official_usd: Официальная цена в USD (Our Price)
        usd_to_rub: Курс USD к RUB
        price_multiplier: Множитель цены (по умолчанию 2.0)
    
    Returns:
        Цена в рублях (округление до копеек, ROUND_HALF_UP)
    """
    effective_multiplier = 1.0 if is_admin else price_multiplier
    price = (
        Decimal(str(official_usd))
        * Decimal(str(usd_to_rub))
        * Decimal(str(effective_multiplier))
    )
    price_quantized = _quantize_decimal(price, 2)
    return float(price_quantized)


def price_for_model_rub(
    model_id: str,
    mode_index: int,
    settings: Settings,
    *,
    is_admin: bool = False,
) -> Optional[int]:
    """
    Рассчитывает цену для конкретной модели и режима в рублях.
    
    Args:
        model_id: ID модели
        mode_index: Индекс режима в списке modes модели
        settings: Настройки приложения
    
    Returns:
        Цена в рублях или None, если модель/режим не найдены
    """
    min_price = get_min_price_rub(model_id)
    if min_price is None:
        logger.warning("Missing pricing SSOT for model %s", model_id)
        return None
    return float(min_price)


def get_model_price_info(
    model_id: str,
    mode_index: int,
    settings: Settings,
    *,
    is_admin: bool = False,
) -> Optional[Dict]:
    """
    Получает полную информацию о цене модели.
    
    Args:
        model_id: ID модели
        mode_index: Индекс режима
        settings: Настройки приложения
    
    Returns:
        Словарь с информацией о цене или None
    """
    model = get_model(model_id)
    if not model:
        return None
    min_price = get_min_price_rub(model_id)
    if min_price is None:
        return None
    return {
        "model_id": model_id,
        "model_title": model.title_ru,
        "mode_index": mode_index,
        "mode_notes": None,
        "unit": None,
        "credits": None,
        "official_usd": None,
        "usd_to_rub": None,
        "price_multiplier": None,
        "price_rub": float(min_price),
    }
