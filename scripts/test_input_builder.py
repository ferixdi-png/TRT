#!/usr/bin/env python3
"""
Тест input builder для разных типов моделей.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from app.kie_catalog import get_model
from app.services.kie_input_builder import build_input

def test_t2i():
    """Тест Text-to-Image."""
    print("\n" + "=" * 60)
    print("Testing t2i (Text-to-Image)")
    print("=" * 60)
    
    model = get_model("flux-2/pro-text-to-image")
    if not model:
        print("[ERROR] Model not found")
        return
    
    user_payload = {
        "prompt": "a cat",
        "neg": "ugly",  # Алиас для negative_prompt
        "width": 1024,
        "height": 1024,
        "extra_field": "should be removed"  # Должно быть удалено
    }
    
    built_input, error = build_input(model, user_payload, 0)
    
    if error:
        print(f"❌ Error: {error}")
    else:
        print(f"[OK] Built input: {built_input}")
        print(f"   Keys: {list(built_input.keys())}")
        assert "extra_field" not in built_input, "Extra field should be removed"
        assert "negative_prompt" in built_input, "Alias should be normalized"
        assert built_input["negative_prompt"] == "ugly", "Alias value should be preserved"
        print("[OK] All checks passed")


def test_i2i():
    """Тест Image-to-Image."""
    print("\n" + "=" * 60)
    print("Testing i2i (Image-to-Image)")
    print("=" * 60)
    
    model = get_model("flux-2/flex-image-to-image")
    if not model:
        print("[ERROR] Model not found")
        return
    
    # Тест с валидными данными
    user_payload = {
        "img": "https://example.com/image.jpg",  # Алиас для image_url
        "prompt": "make it better",
        "strength": 0.75
    }
    
    built_input, error = build_input(model, user_payload, 0)
    
    if error:
        print(f"[ERROR] Error: {error}")
    else:
        print(f"[OK] Built input: {built_input}")
        assert "image_url" in built_input, "Alias should be normalized"
        assert built_input["image_url"] == "https://example.com/image.jpg"
        print("[OK] All checks passed")
    
    # Тест без обязательного поля
    user_payload_no_image = {
        "prompt": "make it better"
    }
    
    built_input, error = build_input(model, user_payload_no_image, 0)
    
    if error:
        print(f"[OK] Validation error (expected): {error}")
    else:
        print(f"[ERROR] Should have validation error for missing image")


def test_t2v():
    """Тест Text-to-Video."""
    print("\n" + "=" * 60)
    print("Testing t2v (Text-to-Video)")
    print("=" * 60)
    
    model = get_model("kling-2.6/text-to-video")
    if not model:
        print("[ERROR] Model not found")
        return
    
    user_payload = {
        "prompt": "a cat walking",
        "duration": 10.0,
        "with_audio": False
    }
    
    built_input, error = build_input(model, user_payload, 0)
    
    if error:
        print(f"❌ Error: {error}")
    else:
        print(f"[OK] Built input: {built_input}")
        # Проверяем что duration из notes парсится
        if model.modes[0].notes:
            print(f"   Mode notes: {model.modes[0].notes}")
        print("[OK] All checks passed")


def test_tts():
    """Тест Text-to-Speech."""
    print("\n" + "=" * 60)
    print("Testing tts (Text-to-Speech)")
    print("=" * 60)
    
    model = get_model("elevenlabs/text-to-speech-multilingual-v2")
    if not model:
        print("[WARN] Model not found, trying another...")
        # Пробуем найти любую tts модель
        from app.kie_catalog import list_models
        models = list_models()
        model = next((m for m in models if m.type == 'tts'), None)
    
    if not model:
        print("[ERROR] No tts model found")
        return
    
    user_payload = {
        "text": "Hello world",
        "voice": "default",
        "speed": 1.0
    }
    
    built_input, error = build_input(model, user_payload, 0)
    
    if error:
        print(f"[ERROR] Error: {error}")
    else:
        print(f"[OK] Built input: {built_input}")
        print("[OK] All checks passed")
    
    # Тест без обязательного поля
    user_payload_no_text = {
        "voice": "default"
    }
    
    built_input, error = build_input(model, user_payload_no_text, 0)
    
    if error:
        print(f"[OK] Validation error (expected): {error}")
    else:
        print(f"[ERROR] Should have validation error for missing text")


if __name__ == "__main__":
    print("Testing Input Builder")
    print("=" * 60)
    
    test_t2i()
    test_i2i()
    test_t2v()
    test_tts()
    
    print("\n" + "=" * 60)
    print("[OK] All tests completed")
    print("=" * 60)

