#!/usr/bin/env python3
"""
Тест загрузки каталога и расчёта цен.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.kie_catalog import load_catalog, get_model, list_models
from app.services.pricing_service import price_for_model_rub, get_model_price_info
from app.config import get_settings

def test_catalog():
    """Тестирует загрузку каталога."""
    print("=" * 60)
    print("Testing KIE Catalog")
    print("=" * 60)
    
    # Загружаем каталог
    catalog = load_catalog()
    print(f"\n[OK] Loaded {len(catalog)} models")
    
    # Проверяем несколько моделей
    test_models = [
        "flux-2/pro-text-to-image",
        "z-image",
        "kling-2.6/text-to-video",
        "sora-2-pro-text-to-video"
    ]
    
    for model_id in test_models:
        model = get_model(model_id)
        if model:
            print(f"\n[Model] {model.title_ru}")
            print(f"   ID: {model.id}")
            print(f"   Type: {model.type}")
            print(f"   Modes: {len(model.modes)}")
            for i, mode in enumerate(model.modes):
                print(f"     [{i}] {mode.unit} - {mode.official_usd}$ USD - {mode.credits} credits")
                if mode.notes:
                    print(f"         Notes: {mode.notes}")
        else:
            print(f"\n[ERROR] Model not found: {model_id}")
    
    # Тестируем расчёт цен
    print("\n" + "=" * 60)
    print("Testing Pricing Service")
    print("=" * 60)
    
    settings = get_settings()
    print(f"\n[Settings]")
    print(f"   USD_TO_RUB: {settings.usd_to_rub}")
    print(f"   PRICE_MULTIPLIER: {settings.price_multiplier}")
    
    # Тестируем расчёт цены
    test_cases = [
        ("flux-2/pro-text-to-image", 0),
        ("z-image", 0),
        ("kling-2.6/text-to-video", 0),
    ]
    
    for model_id, mode_index in test_cases:
        price = price_for_model_rub(model_id, mode_index, settings)
        info = get_model_price_info(model_id, mode_index, settings)
        
        if price:
            print(f"\n[Price] {model_id} (mode {mode_index}):")
            print(f"   Official USD: ${info['official_usd']:.4f}")
            print(f"   Price RUB: {price} RUB")
            print(f"   Formula: ${info['official_usd']:.4f} * {info['usd_to_rub']} * {info['price_multiplier']} = {price} RUB")
        else:
            print(f"\n[ERROR] Failed to calculate price for {model_id}")
    
    print("\n" + "=" * 60)
    print("[OK] All tests completed")
    print("=" * 60)

if __name__ == "__main__":
    test_catalog()

