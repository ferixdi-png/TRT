#!/usr/bin/env python3
"""
Генерация полного файла со всеми моделями KIE AI, режимами и ценами.
"""

import json
from pathlib import Path
from typing import Dict, List, Any

# Курс: 1 USD = 100 RUB (примерно)
USD_TO_RUB = 100

# Все модели с их режимами и ценами
ALL_MODELS_DATA = [
    # Black Forest Labs Flux 2 Flex
    {"model_id": "flux-2/flex-image-to-image", "name": "Flux 2 Flex Image to Image", "mode": "1.0s-1K", "credits": 14.0, "price_usd": 0.07, "price_rub": 0.07 * USD_TO_RUB * 2},
    {"model_id": "flux-2/flex-image-to-image", "name": "Flux 2 Flex Image to Image", "mode": "1.0s-2K", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    {"model_id": "flux-2/flex-text-to-image", "name": "Flux 2 Flex Text to Image", "mode": "1.0s-1K", "credits": 14.0, "price_usd": 0.07, "price_rub": 0.07 * USD_TO_RUB * 2},
    {"model_id": "flux-2/flex-text-to-image", "name": "Flux 2 Flex Text to Image", "mode": "1.0s-2K", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    
    # Black Forest Labs flux-2 pro
    {"model_id": "flux-2/pro-image-to-image", "name": "Flux 2 Pro Image to Image", "mode": "1.0s-1K", "credits": 5.0, "price_usd": 0.025, "price_rub": 0.025 * USD_TO_RUB * 2},
    {"model_id": "flux-2/pro-image-to-image", "name": "Flux 2 Pro Image to Image", "mode": "1.0s-2K", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    {"model_id": "flux-2/pro-text-to-image", "name": "Flux 2 Pro Text to Image", "mode": "1.0s-1K", "credits": 5.0, "price_usd": 0.025, "price_rub": 0.025 * USD_TO_RUB * 2},
    {"model_id": "flux-2/pro-text-to-image", "name": "Flux 2 Pro Text to Image", "mode": "1.0s-2K", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    
    # Black Forest Labs flux1-kontext
    {"model_id": "flux/kontext", "name": "Flux Kontext", "mode": "Pro", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "flux/kontext", "name": "Flux Kontext", "mode": "Max", "credits": 8.0, "price_usd": 0.04, "price_rub": 0.04 * USD_TO_RUB * 2},
    
    # Bytedance Seedance 1.0
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-5.0s-480p", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-5.0s-720p", "credits": 22.5, "price_usd": 0.1125, "price_rub": 0.1125 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-5.0s-1080p", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-10.0s-480p", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-10.0s-720p", "credits": 45.0, "price_usd": 0.225, "price_rub": 0.225 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Lite-10.0s-1080p", "credits": 100.0, "price_usd": 0.5, "price_rub": 0.5 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-5.0s-480p", "credits": 14.0, "price_usd": 0.07, "price_rub": 0.07 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-5.0s-720p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-5.0s-1080p", "credits": 70.0, "price_usd": 0.35, "price_rub": 0.35 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-10.0s-480p", "credits": 28.0, "price_usd": 0.14, "price_rub": 0.14 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-10.0s-720p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro-10.0s-1080p", "credits": 140.0, "price_usd": 0.7, "price_rub": 0.7 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Lite-5.0s-480p", "credits": 14.0, "price_usd": 0.07, "price_rub": 0.07 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Lite-5.0s-720p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Lite-5.0s-1080p", "credits": 70.0, "price_usd": 0.35, "price_rub": 0.35 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Pro-10.0s-480p", "credits": 28.0, "price_usd": 0.14, "price_rub": 0.14 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Pro-10.0s-720p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Text to Video", "mode": "Pro-10.0s-1080p", "credits": 140.0, "price_usd": 0.7, "price_rub": 0.7 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro Fast-5.0s-720p", "credits": 16.0, "price_usd": 0.08, "price_rub": 0.08 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro Fast-10.0s-720p", "credits": 36.0, "price_usd": 0.18, "price_rub": 0.18 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro Fast-5.0s-1080p", "credits": 36.0, "price_usd": 0.18, "price_rub": 0.18 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedance", "name": "Seedance 1.0 Image to Video", "mode": "Pro Fast-10.0s-1080p", "credits": 72.0, "price_usd": 0.36, "price_rub": 0.36 * USD_TO_RUB * 2},
    
    # Bytedance seedance-v1-pro-fast
    {"model_id": "bytedance/v1-pro-fast-image-to-video", "name": "Seedance V1 Pro Fast Image to Video", "mode": "Fast-5.0s-720p", "credits": 16.0, "price_usd": 0.08, "price_rub": 0.08 * USD_TO_RUB * 2},
    {"model_id": "bytedance/v1-pro-fast-image-to-video", "name": "Seedance V1 Pro Fast Image to Video", "mode": "Fast-10.0s-720p", "credits": 36.0, "price_usd": 0.18, "price_rub": 0.18 * USD_TO_RUB * 2},
    {"model_id": "bytedance/v1-pro-fast-image-to-video", "name": "Seedance V1 Pro Fast Image to Video", "mode": "Fast-5.0s-1080p", "credits": 36.0, "price_usd": 0.18, "price_rub": 0.18 * USD_TO_RUB * 2},
    {"model_id": "bytedance/v1-pro-fast-image-to-video", "name": "Seedance V1 Pro Fast Image to Video", "mode": "Fast-10.0s-1080p", "credits": 72.0, "price_usd": 0.36, "price_rub": 0.36 * USD_TO_RUB * 2},
    
    # ByteDance Seedream
    {"model_id": "bytedance/seedream", "name": "Seedream 3.0 Text to Image", "mode": "default", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedream", "name": "Seedream 4.0 Image to Video", "mode": "default", "credits": 5.0, "price_usd": 0.025, "price_rub": 0.025 * USD_TO_RUB * 2},
    {"model_id": "bytedance/seedream", "name": "Seedream 4.0 Text to Image", "mode": "default", "credits": 5.0, "price_usd": 0.025, "price_rub": 0.025 * USD_TO_RUB * 2},
    {"model_id": "seedream/4.5-text-to-image", "name": "Seedream 4.5 Text to Image", "mode": "Basic", "credits": 6.5, "price_usd": 0.0325, "price_rub": 0.0325 * USD_TO_RUB * 2},
    {"model_id": "seedream/4.5-text-to-image", "name": "Seedream 4.5 Text to Image", "mode": "High", "credits": 6.5, "price_usd": 0.0325, "price_rub": 0.0325 * USD_TO_RUB * 2},
    {"model_id": "seedream/4.5-edit", "name": "Seedream 4.5 Image Edit", "mode": "Basic", "credits": 6.5, "price_usd": 0.0325, "price_rub": 0.0325 * USD_TO_RUB * 2},
    {"model_id": "seedream/4.5-edit", "name": "Seedream 4.5 Image Edit", "mode": "High", "credits": 6.5, "price_usd": 0.0325, "price_rub": 0.0325 * USD_TO_RUB * 2},
    
    # Elevenlabs
    {"model_id": "elevenlabs/audio-isolation", "name": "Elevenlabs Audio Isolation", "mode": "default", "credits": 0.2, "price_usd": 0.001, "price_rub": 0.001 * USD_TO_RUB * 2},
    {"model_id": "elevenlabs/sound-effect", "name": "Elevenlabs Sound Effect V2", "mode": "default", "credits": 0.24, "price_usd": 0.0012, "price_rub": 0.0012 * USD_TO_RUB * 2},
    {"model_id": "elevenlabs/speech-to-text", "name": "Elevenlabs Speech to Text", "mode": "default", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "elevenlabs/text-to-speech", "name": "Elevenlabs Text to Speech Multilingual v2", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "elevenlabs/text-to-speech", "name": "Elevenlabs Text to Speech Turbo 2.5", "mode": "turbo", "credits": 6.0, "price_usd": 0.03, "price_rub": 0.03 * USD_TO_RUB * 2},
    
    # Google Imagen
    {"model_id": "google/imagen4", "name": "Google Imagen 4", "mode": "Ultra", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "google/imagen4-fast", "name": "Google Imagen 4 Fast", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "google/imagen4-ultra", "name": "Google Imagen 4", "mode": "default", "credits": 8.0, "price_usd": 0.04, "price_rub": 0.04 * USD_TO_RUB * 2},
    {"model_id": "google/nano-banana", "name": "Google Nano Banana Text to Image", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "google/nano-banana-edit", "name": "Google Nano Banana Edit", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "google/nano-banana-pro", "name": "Google Nano Banana Pro", "mode": "1.0s-1K", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "google/nano-banana-pro", "name": "Google Nano Banana Pro", "mode": "1.0s-2K", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "google/nano-banana-pro", "name": "Google Nano Banana Pro", "mode": "1.0s-4K", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    
    # Google Veo
    {"model_id": "google/veo-3", "name": "Google Veo 3 Text to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3", "name": "Google Veo 3 Text to Video", "mode": "Quality", "credits": 250.0, "price_usd": 1.25, "price_rub": 1.25 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3", "name": "Google Veo 3 Image to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3", "name": "Google Veo 3 Image to Video", "mode": "Quality", "credits": 250.0, "price_usd": 1.25, "price_rub": 1.25 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3", "name": "Google Veo 3 Reference to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3.1", "name": "Google Veo 3.1 Text to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3.1", "name": "Google Veo 3.1 Text to Video", "mode": "Quality", "credits": 250.0, "price_usd": 1.25, "price_rub": 1.25 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3.1", "name": "Google Veo 3.1 Image to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3.1", "name": "Google Veo 3.1 Image to Video", "mode": "Quality", "credits": 250.0, "price_usd": 1.25, "price_rub": 1.25 * USD_TO_RUB * 2},
    {"model_id": "google/veo-3.1", "name": "Google Veo 3.1 Reference to Video", "mode": "Fast", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    
    # Grok Imagine
    {"model_id": "grok/imagine", "name": "Grok Imagine Image to Video", "mode": "6.0s", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "grok/imagine", "name": "Grok Imagine Text to Video", "mode": "6.0s", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "grok/imagine", "name": "Grok Imagine Text to Image", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "grok/imagine", "name": "Grok Imagine Upscale", "mode": "360p→720p", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    
    # Hailuo
    {"model_id": "hailuo/02-image-to-video-standard", "name": "Hailuo 02 Image to Video", "mode": "Pro-6.0s-1080p", "credits": 57.0, "price_usd": 0.285, "price_rub": 0.285 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-text-to-video-standard", "name": "Hailuo 02 Text to Video", "mode": "Pro-6.0s-1080p", "credits": 57.0, "price_usd": 0.285, "price_rub": 0.285 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-image-to-video-standard", "name": "Hailuo 02 Image to Video", "mode": "Standard-6.0s-512p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-image-to-video-standard", "name": "Hailuo 02 Image to Video", "mode": "Standard-10.0s-512p", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-image-to-video-standard", "name": "Hailuo 02 Image to Video", "mode": "Standard-10.0s-768p", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-text-to-video-standard", "name": "Hailuo 02 Text to Video", "mode": "Standard-6.0s-768p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "hailuo/02-text-to-video-standard", "name": "Hailuo 02 Text to Video", "mode": "Standard-10.0s-768p", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Standard-6.0s-768p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Standard-10.0s-768p", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Standard-6.0s-1080p", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Pro-6.0s-768p", "credits": 45.0, "price_usd": 0.225, "price_rub": 0.225 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Pro-10.0s-768p", "credits": 90.0, "price_usd": 0.45, "price_rub": 0.45 * USD_TO_RUB * 2},
    {"model_id": "hailuo/2.3", "name": "Hailuo 2.3 Image to Video", "mode": "Pro-6.0s-1080p", "credits": 80.0, "price_usd": 0.4, "price_rub": 0.4 * USD_TO_RUB * 2},
    
    # Ideogram
    {"model_id": "ideogram/v3-text-to-image", "name": "Ideogram V3 Text to Image", "mode": "TURBO", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-text-to-image", "name": "Ideogram V3 Text to Image", "mode": "BALANCED", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-text-to-image", "name": "Ideogram V3 Text to Image", "mode": "QUALITY", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-reframe", "name": "Ideogram V3 Reframe", "mode": "Turbo", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-reframe", "name": "Ideogram V3 Reframe", "mode": "Balanced", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-reframe", "name": "Ideogram V3 Reframe", "mode": "Quality", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-edit", "name": "Ideogram V3 Edit", "mode": "TURBO", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-edit", "name": "Ideogram V3 Edit", "mode": "BALANCED", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-edit", "name": "Ideogram V3 Edit", "mode": "QUALITY", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-remix", "name": "Ideogram V3 Remix", "mode": "TURBO", "credits": 3.5, "price_usd": 0.0175, "price_rub": 0.0175 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-remix", "name": "Ideogram V3 Remix", "mode": "BALANCED", "credits": 7.0, "price_usd": 0.035, "price_rub": 0.035 * USD_TO_RUB * 2},
    {"model_id": "ideogram/v3-remix", "name": "Ideogram V3 Remix", "mode": "QUALITY", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character", "name": "Ideogram Character", "mode": "TURBO", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character", "name": "Ideogram Character", "mode": "BALANCED", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character", "name": "Ideogram Character", "mode": "QUALITY", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-edit", "name": "Ideogram Character Edit", "mode": "TURBO", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-edit", "name": "Ideogram Character Edit", "mode": "BALANCED", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-edit", "name": "Ideogram Character Edit", "mode": "QUALITY", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-remix", "name": "Ideogram Character Remix", "mode": "TURBO", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-remix", "name": "Ideogram Character Remix", "mode": "BALANCED", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "ideogram/character-remix", "name": "Ideogram Character Remix", "mode": "QUALITY", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    
    # Kling
    {"model_id": "kling/v2-1-master-image-to-video", "name": "Kling 2.1 Image to Video", "mode": "Master-5.0s", "credits": 160.0, "price_usd": 0.8, "price_rub": 0.8 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-master-image-to-video", "name": "Kling 2.1 Image to Video", "mode": "Master-10.0s", "credits": 320.0, "price_usd": 1.6, "price_rub": 1.6 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-standard", "name": "Kling 2.1 Video Generation", "mode": "Standard-5.0s", "credits": 25.0, "price_usd": 0.125, "price_rub": 0.125 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-standard", "name": "Kling 2.1 Video Generation", "mode": "Standard-10.0s", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-pro", "name": "Kling 2.1 Video Generation", "mode": "Pro-5.0s", "credits": 50.0, "price_usd": 0.25, "price_rub": 0.25 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-pro", "name": "Kling 2.1 Video Generation", "mode": "Pro-10.0s", "credits": 100.0, "price_usd": 0.5, "price_rub": 0.5 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-master-text-to-video", "name": "Kling 2.1 Text to Video", "mode": "Master-5.0s", "credits": 160.0, "price_usd": 0.8, "price_rub": 0.8 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-1-master-text-to-video", "name": "Kling 2.1 Text to Video", "mode": "Master-10.0s", "credits": 320.0, "price_usd": 1.6, "price_rub": 1.6 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-5-turbo-image-to-video-pro", "name": "Kling 2.5 Turbo Image to Video", "mode": "Turbo Pro-5.0s", "credits": 42.0, "price_usd": 0.21, "price_rub": 0.21 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-5-turbo-image-to-video-pro", "name": "Kling 2.5 Turbo Image to Video", "mode": "Turbo Pro-10.0s", "credits": 84.0, "price_usd": 0.42, "price_rub": 0.42 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-5-turbo-text-to-video-pro", "name": "Kling 2.5 Turbo Text to Video", "mode": "Turbo Pro-5.0s", "credits": 42.0, "price_usd": 0.21, "price_rub": 0.21 * USD_TO_RUB * 2},
    {"model_id": "kling/v2-5-turbo-text-to-video-pro", "name": "Kling 2.5 Turbo Text to Video", "mode": "Turbo Pro-10.0s", "credits": 84.0, "price_usd": 0.42, "price_rub": 0.42 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/image-to-video", "name": "Kling 2.6 Image to Video", "mode": "without audio-5.0s", "credits": 55.0, "price_usd": 0.275, "price_rub": 0.275 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/image-to-video", "name": "Kling 2.6 Image to Video", "mode": "with audio-5.0s", "credits": 110.0, "price_usd": 0.55, "price_rub": 0.55 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/image-to-video", "name": "Kling 2.6 Image to Video", "mode": "without audio-10.0s", "credits": 110.0, "price_usd": 0.55, "price_rub": 0.55 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/image-to-video", "name": "Kling 2.6 Image to Video", "mode": "with audio-10.0s", "credits": 220.0, "price_usd": 1.1, "price_rub": 1.1 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/text-to-video", "name": "Kling 2.6 Text to Video", "mode": "without audio-5.0s", "credits": 55.0, "price_usd": 0.275, "price_rub": 0.275 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/text-to-video", "name": "Kling 2.6 Text to Video", "mode": "with audio-5.0s", "credits": 110.0, "price_usd": 0.55, "price_rub": 0.55 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/text-to-video", "name": "Kling 2.6 Text to Video", "mode": "without audio-10.0s", "credits": 110.0, "price_usd": 0.55, "price_rub": 0.55 * USD_TO_RUB * 2},
    {"model_id": "kling-2.6/text-to-video", "name": "Kling 2.6 Text to Video", "mode": "with audio-10.0s", "credits": 220.0, "price_usd": 1.1, "price_rub": 1.1 * USD_TO_RUB * 2},
    {"model_id": "kling/v1-avatar-standard", "name": "Kling AI Avatar Lip Sync", "mode": "Standard-up to 15 secondss-720p", "credits": 8.0, "price_usd": 0.04, "price_rub": 0.04 * USD_TO_RUB * 2},
    {"model_id": "kling/ai-avatar-v1-pro", "name": "Kling AI Avatar Lip Sync", "mode": "Pro-up to 15 secondss-1080p", "credits": 16.0, "price_usd": 0.08, "price_rub": 0.08 * USD_TO_RUB * 2},
    
    # MeiGen-AI
    {"model_id": "infinitalk/from-audio", "name": "MeiGen-AI InfiniteTalk Lip Sync", "mode": "up to 15 secondss-480p", "credits": 3.0, "price_usd": 0.015, "price_rub": 0.015 * USD_TO_RUB * 2},
    {"model_id": "infinitalk/from-audio", "name": "MeiGen-AI InfiniteTalk Lip Sync", "mode": "up to 15 secondss-720p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    
    # Midjourney
    {"model_id": "midjourney/api", "name": "Midjourney Text to Image", "mode": "relaxed", "credits": 3.0, "price_usd": 0.015, "price_rub": 0.015 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Text to Image", "mode": "fast", "credits": 8.0, "price_usd": 0.04, "price_rub": 0.04 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Text to Image", "mode": "turbo", "credits": 16.0, "price_usd": 0.08, "price_rub": 0.08 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Image to Image", "mode": "relaxed", "credits": 3.0, "price_usd": 0.015, "price_rub": 0.015 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Image to Image", "mode": "fast", "credits": 8.0, "price_usd": 0.04, "price_rub": 0.04 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Image to Image", "mode": "turbo", "credits": 16.0, "price_usd": 0.08, "price_rub": 0.08 * USD_TO_RUB * 2},
    {"model_id": "midjourney/api", "name": "Midjourney Image to Video", "mode": "default", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    
    # OpenAI Sora
    {"model_id": "sora-2-text-to-video", "name": "OpenAI Sora 2 Text to Video", "mode": "Standard-10.0s", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "sora-2-text-to-video", "name": "OpenAI Sora 2 Text to Video", "mode": "Standard-15.0s", "credits": 25.0, "price_usd": 0.125, "price_rub": 0.125 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Image to Video", "mode": "Standard-10.0s", "credits": 20.0, "price_usd": 0.1, "price_rub": 0.1 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Image to Video", "mode": "Standard-15.0s", "credits": 25.0, "price_usd": 0.125, "price_rub": 0.125 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-storyboard", "name": "OpenAI Sora 2 Pro Storyboard", "mode": "Pro-10.0s", "credits": 150.0, "price_usd": 0.75, "price_rub": 0.75 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-storyboard", "name": "OpenAI Sora 2 Pro Storyboard", "mode": "Pro-15-25s", "credits": 270.0, "price_usd": 1.35, "price_rub": 1.35 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-text-to-video", "name": "OpenAI Sora 2 Pro Text to Video", "mode": "Pro Standard-10.0s", "credits": 150.0, "price_usd": 0.75, "price_rub": 0.75 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-text-to-video", "name": "OpenAI Sora 2 Pro Text to Video", "mode": "Pro Standard-15.0s", "credits": 270.0, "price_usd": 1.35, "price_rub": 1.35 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-text-to-video", "name": "OpenAI Sora 2 Pro Text to Video", "mode": "Pro High-10.0s", "credits": 330.0, "price_usd": 1.65, "price_rub": 1.65 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-text-to-video", "name": "OpenAI Sora 2 Pro Text to Video", "mode": "Pro High-15.0s", "credits": 630.0, "price_usd": 3.15, "price_rub": 3.15 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Pro Image to Video", "mode": "Pro Standard-10.0s", "credits": 150.0, "price_usd": 0.75, "price_rub": 0.75 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Pro Image to Video", "mode": "Pro Standard-15.0s", "credits": 270.0, "price_usd": 1.35, "price_rub": 1.35 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Pro Image to Video", "mode": "Pro High-10.0s", "credits": 330.0, "price_usd": 1.65, "price_rub": 1.65 * USD_TO_RUB * 2},
    {"model_id": "sora-2-pro-image-to-video", "name": "OpenAI Sora 2 Pro Image to Video", "mode": "Pro High-15.0s", "credits": 630.0, "price_usd": 3.15, "price_rub": 3.15 * USD_TO_RUB * 2},
    {"model_id": "sora-watermark-remover", "name": "OpenAI Sora 2 Watermark Remover", "mode": "default", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    
    # OpenAI 4o
    {"model_id": "openai/4o-image", "name": "OpenAI 4o Image Text to Image", "mode": "default", "credits": 6.0, "price_usd": 0.03, "price_rub": 0.03 * USD_TO_RUB * 2},
    
    # Qwen
    {"model_id": "qwen/image-to-image", "name": "Qwen Image Image to Image", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "qwen/text-to-image", "name": "Qwen Image Text to Image", "mode": "default", "credits": 4.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "qwen/image-edit", "name": "Qwen Image Edit", "mode": "default", "credits": 5.0, "price_usd": 0.03, "price_rub": 0.03 * USD_TO_RUB * 2},
    {"model_id": "z-image", "name": "Qwen Z-Image Text to Image", "mode": "1.0s", "credits": 0.8, "price_usd": 0.004, "price_rub": 0.004 * USD_TO_RUB * 2},
    
    # Recraft
    {"model_id": "recraft/crisp-upscale", "name": "Recraft Crisp Upscale", "mode": "default", "credits": 0.5, "price_usd": 0.0025, "price_rub": 0.0025 * USD_TO_RUB * 2},
    {"model_id": "recraft/remove-background", "name": "Recraft Remove Background", "mode": "default", "credits": 1.0, "price_usd": 0.005, "price_rub": 0.005 * USD_TO_RUB * 2},
    
    # Runway
    {"model_id": "runway/gen-4", "name": "Runway Image to Video", "mode": "5.0s-720p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "runway/gen-4", "name": "Runway Image to Video", "mode": "10.0s-720p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "runway/gen-4", "name": "Runway Image to Video", "mode": "5.0s-1080p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "runway/gen-4", "name": "Runway Text to Video", "mode": "5.0s-720p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "runway/gen-4", "name": "Runway Text to Video", "mode": "10.0s-720p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    {"model_id": "runway/gen-4", "name": "Runway Text to Video", "mode": "5.0s-1080p", "credits": 30.0, "price_usd": 0.15, "price_rub": 0.15 * USD_TO_RUB * 2},
    
    # Suno
    {"model_id": "suno/v5", "name": "Suno Generate Music", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Extend Music", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Add Vocals", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Add Instrumental", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Create Music Video", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Upload and Extend Audio", "mode": "default", "credits": 2.0, "price_usd": 0.01, "price_rub": 0.01 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Upload and Cover Audio", "mode": "default", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Convert to WAV Format", "mode": "default", "credits": 0.4, "price_usd": 0.002, "price_rub": 0.002 * USD_TO_RUB * 2},
    {"model_id": "suno/v5", "name": "Suno Generate Lyrics", "mode": "default", "credits": 0.4, "price_usd": 0.002, "price_rub": 0.002 * USD_TO_RUB * 2},
    
    # Topaz
    {"model_id": "topaz/image-upscale", "name": "Topaz Image Upscaler", "mode": "≤2K", "credits": 10.0, "price_usd": 0.05, "price_rub": 0.05 * USD_TO_RUB * 2},
    {"model_id": "topaz/image-upscale", "name": "Topaz Image Upscaler", "mode": "4K", "credits": 20.0, "price_usd": 0.01, "price_rub": 0.01 * USD_TO_RUB * 2},
    {"model_id": "topaz/image-upscale", "name": "Topaz Image Upscaler", "mode": "8K", "credits": 40.0, "price_usd": 0.02, "price_rub": 0.02 * USD_TO_RUB * 2},
    {"model_id": "topaz/video-upscale", "name": "Topaz Video Upscaler", "mode": "upscale factor 1x/2x/4xs", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    
    # Wan
    {"model_id": "wan/2-2-a14b-text-to-video-turbo", "name": "Wan 2.2 Text to Video", "mode": "5.0s-720p", "credits": 80.0, "price_usd": 0.4, "price_rub": 0.4 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-text-to-video-turbo", "name": "Wan 2.2 Text to Video", "mode": "5.0s-580p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-text-to-video-turbo", "name": "Wan 2.2 Text to Video", "mode": "5.0s-480p", "credits": 40.0, "price_usd": 0.2, "price_rub": 0.2 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-image-to-video-turbo", "name": "Wan 2.2 Image to Video", "mode": "5.0s-720p", "credits": 80.0, "price_usd": 0.4, "price_rub": 0.4 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-image-to-video-turbo", "name": "Wan 2.2 Image to Video", "mode": "5.0s-580p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-image-to-video-turbo", "name": "Wan 2.2 Image to Video", "mode": "5.0s-480p", "credits": 40.0, "price_usd": 0.2, "price_rub": 0.2 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-speech-to-video-turbo", "name": "Wan 2.2 A14B Turbo API Speech to Video", "mode": "720p", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-speech-to-video-turbo", "name": "Wan 2.2 A14B Turbo API Speech to Video", "mode": "580p", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-a14b-speech-to-video-turbo", "name": "Wan 2.2 A14B Turbo API Speech to Video", "mode": "480p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-animate-move", "name": "Wan 2.2 Animate Speech to Video", "mode": "Turbo-1.0s-720p", "credits": 24.0, "price_usd": 0.12, "price_rub": 0.12 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-animate-move", "name": "Wan 2.2 Animate Speech to Video", "mode": "Turbo-1.0s-580p", "credits": 18.0, "price_usd": 0.09, "price_rub": 0.09 * USD_TO_RUB * 2},
    {"model_id": "wan/2-2-animate-move", "name": "Wan 2.2 Animate Speech to Video", "mode": "Turbo-1.0s-480p", "credits": 12.0, "price_usd": 0.06, "price_rub": 0.06 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-image-to-video", "name": "Wan 2.5 Image to Video", "mode": "default-5.0s-720p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-image-to-video", "name": "Wan 2.5 Image to Video", "mode": "default-10.0s-720p", "credits": 120.0, "price_usd": 0.6, "price_rub": 0.6 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-image-to-video", "name": "Wan 2.5 Image to Video", "mode": "default-5.0s-1080p", "credits": 100.0, "price_usd": 0.5, "price_rub": 0.5 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-image-to-video", "name": "Wan 2.5 Image to Video", "mode": "default-10.0s-1080p", "credits": 200.0, "price_usd": 1.0, "price_rub": 1.0 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-text-to-video", "name": "Wan 2.5 Text to Video", "mode": "default-5.0s-720p", "credits": 60.0, "price_usd": 0.3, "price_rub": 0.3 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-text-to-video", "name": "Wan 2.5 Text to Video", "mode": "default-10.0s-720p", "credits": 120.0, "price_usd": 0.6, "price_rub": 0.6 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-text-to-video", "name": "Wan 2.5 Text to Video", "mode": "default-5.0s-1080p", "credits": 100.0, "price_usd": 0.5, "price_rub": 0.5 * USD_TO_RUB * 2},
    {"model_id": "wan/2-5-text-to-video", "name": "Wan 2.5 Text to Video", "mode": "default-10.0s-1080p", "credits": 200.0, "price_usd": 1.0, "price_rub": 1.0 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "5.0s-720p", "credits": 70.0, "price_usd": 0.35, "price_rub": 0.35 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "10.0s-720p", "credits": 140.0, "price_usd": 0.7, "price_rub": 0.7 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "15.0s-720p", "credits": 210.0, "price_usd": 1.05, "price_rub": 1.05 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "5.0s-1080p", "credits": 104.5, "price_usd": 0.5225, "price_rub": 0.5225 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "10.0s-1080p", "credits": 209.5, "price_usd": 1.0475, "price_rub": 1.0475 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-text-to-video", "name": "Wan 2.6 Text to Video", "mode": "15.0s-1080p", "credits": 315.0, "price_usd": 1.575, "price_rub": 1.575 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "5.0s-720p", "credits": 70.0, "price_usd": 0.35, "price_rub": 0.35 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "10.0s-720p", "credits": 140.0, "price_usd": 0.7, "price_rub": 0.7 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "15.0s-720p", "credits": 210.0, "price_usd": 1.05, "price_rub": 1.05 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "5.0s-1080p", "credits": 104.5, "price_usd": 0.5225, "price_rub": 0.5225 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "10.0s-1080p", "credits": 209.5, "price_usd": 1.0475, "price_rub": 1.0475 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-image-to-video", "name": "Wan 2.6 Image to Video", "mode": "15.0s-1080p", "credits": 315.0, "price_usd": 1.575, "price_rub": 1.575 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "5.0s-720p", "credits": 70.0, "price_usd": 0.35, "price_rub": 0.35 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "10.0s-720p", "credits": 140.0, "price_usd": 0.7, "price_rub": 0.7 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "15.0s-720p", "credits": 210.0, "price_usd": 1.05, "price_rub": 1.05 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "5.0s-1080p", "credits": 104.5, "price_usd": 0.5225, "price_rub": 0.5225 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "10.0s-1080p", "credits": 209.5, "price_usd": 1.0475, "price_rub": 1.0475 * USD_TO_RUB * 2},
    {"model_id": "wan/2-6-video-to-video", "name": "Wan 2.6 Video to Video", "mode": "15.0s-1080p", "credits": 315.0, "price_usd": 1.575, "price_rub": 1.575 * USD_TO_RUB * 2},
]

def group_by_model(models_data: List[Dict]) -> Dict[str, List[Dict]]:
    """Группирует модели по model_id."""
    grouped = {}
    for model in models_data:
        model_id = model["model_id"]
        if model_id not in grouped:
            grouped[model_id] = []
        grouped[model_id].append(model)
    return grouped

def generate_complete_pricing_file():
    """Генерирует полный файл с ценами."""
    root_dir = Path(__file__).parent.parent
    output_file = root_dir / "data" / "kie_models_complete_pricing.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Группируем по моделям
    grouped_models = group_by_model(ALL_MODELS_DATA)
    
    # Формируем структуру
    result = {
        "timestamp": "2025-12-21T20:00:00Z",
        "currency": {
            "usd_to_rub": USD_TO_RUB,
            "multiplier": 2,
            "note": "Цены в рублях = Our Price (USD) * USD_TO_RUB * 2"
        },
        "total_models": len(grouped_models),
        "total_modes": len(ALL_MODELS_DATA),
        "models": {}
    }
    
    for model_id, modes in grouped_models.items():
        model_info = {
            "model_id": model_id,
            "name": modes[0]["name"].split(",")[0] if "," in modes[0]["name"] else modes[0]["name"],
            "modes": []
        }
        
        for mode_data in modes:
            model_info["modes"].append({
                "mode": mode_data["mode"],
                "credits_per_generation": mode_data["credits"],
                "price_usd": round(mode_data["price_usd"], 4),
                "price_rub": round(mode_data["price_rub"], 2)
            })
        
        result["models"][model_id] = model_info
    
    # Сохраняем
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"File created: {output_file}")
    print(f"Total models: {result['total_models']}")
    print(f"Total modes: {result['total_modes']}")
    
    return output_file

if __name__ == "__main__":
    generate_complete_pricing_file()

