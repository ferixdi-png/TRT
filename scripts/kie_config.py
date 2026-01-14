#!/usr/bin/env python3
"""
KIE Configuration - единый источник конфигурации для KIE sync/verify.

Загружает конфигурацию из environment variables или config файла.
Запрещает "тихие" дефолты - требует явного указания критических параметров.

ИСПОЛЬЗОВАНИЕ:
    from scripts.kie_config import get_usd_to_rub_rate, calculate_rub_price, KIEConfigError
    
    try:
        rate = get_usd_to_rub_rate()  # Raises KIEConfigError if not set
        rub_price = calculate_rub_price(0.05, markup_multiplier=2.0)
    except KIEConfigError as e:
        print(f"Configuration error: {e}")
"""

import os
from pathlib import Path
from typing import Optional
from decimal import Decimal


class KIEConfigError(Exception):
    """Ошибка конфигурации KIE."""
    pass


def get_usd_to_rub_rate() -> Decimal:
    """
    Получает курс USD к RUB из единого источника.
    
    Источники (в порядке приоритета):
    1. Environment variable: USD_TO_RUB
    2. Desktop/TRT_RENDER.env: USD_TO_RUB
    3. .env файл в корне проекта: USD_TO_RUB
    
    Raises:
        KIEConfigError: если курс не установлен
    
    Returns:
        Decimal: курс USD к RUB
    """
    # 1. Environment variable
    usd_to_rub = os.getenv("USD_TO_RUB")
    if usd_to_rub:
        try:
            rate = Decimal(str(usd_to_rub).strip())
            if rate <= 0:
                raise KIEConfigError(f"USD_TO_RUB must be positive, got: {rate}")
            return rate
        except (ValueError, TypeError) as e:
            raise KIEConfigError(f"Invalid USD_TO_RUB format: {usd_to_rub}") from e
    
    # 2. Desktop/TRT_RENDER.env
    if os.name == 'nt':  # Windows
        desktop_path = Path(os.getenv('USERPROFILE', '')) / 'Desktop'
    else:  # macOS/Linux
        desktop_path = Path.home() / 'Desktop'
    
    env_file = desktop_path / 'TRT_RENDER.env'
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('USD_TO_RUB='):
                    value = line.split('=', 1)[1].strip()
                    try:
                        rate = Decimal(value)
                        if rate <= 0:
                            raise KIEConfigError(f"USD_TO_RUB must be positive, got: {rate}")
                        return rate
                    except (ValueError, TypeError) as e:
                        raise KIEConfigError(f"Invalid USD_TO_RUB format in {env_file}: {value}") from e
    
    # 3. .env файл в корне проекта
    project_root = Path(__file__).parent.parent
    dotenv_file = project_root / '.env'
    if dotenv_file.exists():
        with open(dotenv_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('USD_TO_RUB='):
                    value = line.split('=', 1)[1].strip()
                    try:
                        rate = Decimal(value)
                        if rate <= 0:
                            raise KIEConfigError(f"USD_TO_RUB must be positive, got: {rate}")
                        return rate
                    except (ValueError, TypeError) as e:
                        raise KIEConfigError(f"Invalid USD_TO_RUB format in {dotenv_file}: {value}") from e
    
    # Нет дефолта - требуем явного указания
    raise KIEConfigError(
        "USD_TO_RUB not found. Set it in:\n"
        "  1. Environment variable: export USD_TO_RUB=100.0\n"
        "  2. Desktop/TRT_RENDER.env: USD_TO_RUB=100.0\n"
        "  3. .env file in project root: USD_TO_RUB=100.0"
    )


def calculate_rub_price(usd_price: float, markup_multiplier: float = 2.0) -> float:
    """
    Рассчитывает цену в RUB из USD с учетом маржи.
    
    Formula: RUB = USD * markup_multiplier * USD_TO_RUB
    
    Args:
        usd_price: Цена в USD
        markup_multiplier: Множитель маржи (по умолчанию 2.0)
    
    Returns:
        float: Цена в RUB (округленная до 2 знаков)
    
    Raises:
        KIEConfigError: если USD_TO_RUB не установлен
    """
    usd_to_rub = get_usd_to_rub_rate()
    rub_price = float(Decimal(str(usd_price)) * Decimal(str(markup_multiplier)) * usd_to_rub)
    return round(rub_price, 2)


if __name__ == "__main__":
    """Test configuration loading."""
    try:
        rate = get_usd_to_rub_rate()
        print(f"✅ USD_TO_RUB = {rate}")
    except KIEConfigError as e:
        print(f"❌ {e}")
        exit(1)

