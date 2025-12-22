# 📚 Индекс официальной документации KIE AI API

> **ВАЖНО**: Все инструкции в этом файле являются официальными правилами генерации. Интеграция должна строго следовать этим правилам "по гарантии по закону".

## 🎯 Назначение

Этот файл содержит индекс всех официальных инструкций по API моделей KIE AI. Каждая модель должна быть интегрирована строго согласно предоставленной документации.

## 📋 Правила работы с документацией

1. **Все инструкции фиксируются** - каждая предоставленная документация сохраняется "по гарантии по закону"
2. **Строгое соответствие** - интеграция должна точно следовать правилам из документации
3. **Валидация обязательна** - все параметры проверяются согласно документации
4. **Дефолтные значения** - применяются строго как указано в документации
5. **Генерации проходят по правилам** - все генерации должны проходить строго по этим инструкциям

## 📖 Список интегрированных моделей

### ✅ Sora 2 Pro Models

- [x] **sora-2-pro-storyboard** - `docs/SORA_2_PRO_STORYBOARD_INTEGRATION.md`
  - Обязательные: `n_frames` ("10" | "15" | "25")
  - Опциональные: `image_urls`, `aspect_ratio` ("portrait" | "landscape")
  - Default: `n_frames="15"`, `aspect_ratio="landscape"`

- [x] **sora-2-pro-text-to-video** - `docs/SORA_2_PRO_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000 chars)
  - Опциональные: `aspect_ratio`, `n_frames` ("10" | "15"), `size` ("standard" | "high"), `remove_watermark` (boolean)
  - Default: `aspect_ratio="landscape"`, `n_frames="10"`, `size="high"`, `remove_watermark=true`

- [x] **sora-2-pro-image-to-video** - `docs/SORA_2_PRO_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000 chars), `image_urls` (array)
  - Опциональные: `aspect_ratio`, `n_frames` ("10" | "15"), `size` ("standard" | "high"), `remove_watermark` (boolean)
  - Default: `aspect_ratio="landscape"`, `n_frames="10"`, `size="standard"`, `remove_watermark=true`
  - **ВАЖНО**: `size` default "standard" (отличается от text-to-video, где "high"!)

### ✅ Sora 2 Models (Non-Pro)

- [x] **sora-2-text-to-video** - `docs/SORA_2_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000 chars)
  - Опциональные: `aspect_ratio`, `n_frames` ("10" | "15"), `remove_watermark` (boolean)
  - Default: `aspect_ratio="landscape"`, `n_frames="10"`, `remove_watermark=true`
  - **ВАЖНО**: НЕТ параметра `size` (в отличие от pro версии!)

- [x] **sora-2-image-to-video** - `docs/SORA_2_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000 chars), `image_urls` (array)
  - Опциональные: `aspect_ratio`, `n_frames` ("10" | "15"), `remove_watermark` (boolean)
  - Default: `aspect_ratio="landscape"`, `n_frames="10"`, `remove_watermark=true`
  - **ВАЖНО**: НЕТ параметра `size` (в отличие от pro версии!)

### ✅ Sora Watermark Remover

- [x] **sora-watermark-remover** - `docs/SORA_WATERMARK_REMOVER_INTEGRATION.md`
  - Обязательные: `video_url` (должен начинаться с `sora.chatgpt.com`, max 500 chars)
  - Default: `video_url="https://sora.chatgpt.com/p/s_68e83bd7eee88191be79d2ba7158516f"`

### ✅ WAN Models

- [x] **wan/2-6-text-to-video** - `docs/WAN_2_6_TEXT_TO_VIDEO_INTEGRATION.md`
- [x] **wan/2-6-image-to-video** - `docs/WAN_2_6_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **wan/2-6-video-to-video** - `docs/WAN_2_6_VIDEO_TO_VIDEO_INTEGRATION.md`

### ✅ Seedream Models

- [x] **seedream/4.5-text-to-image** - `docs/SEEDREAM_4_5_TEXT_TO_IMAGE_INTEGRATION.md`
- [x] **seedream/4.5-edit** - `docs/SEEDREAM_4_5_EDIT_INTEGRATION.md`

### ✅ Kling Models

- [x] **kling-2.6/image-to-video** - `docs/KLING_2_6_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **kling-2.6/text-to-video** - `docs/KLING_2_6_TEXT_TO_VIDEO_INTEGRATION.md`

### ✅ Flux Models

- [x] **flux-2/pro-image-to-image** - `docs/FLUX_2_PRO_IMAGE_TO_IMAGE_INTEGRATION.md`
- [x] **flux-2/pro-text-to-image** - `docs/FLUX_2_PRO_TEXT_TO_IMAGE_INTEGRATION.md`
- [x] **flux-2/flex-image-to-image** - `docs/FLUX_2_FLEX_IMAGE_TO_IMAGE_INTEGRATION.md`
- [x] **flux-2/flex-text-to-image** - `docs/FLUX_2_FLEX_TEXT_TO_IMAGE_INTEGRATION.md`

### ✅ Other Models

- [x] **z-image** - `docs/Z_IMAGE_INTEGRATION.md`
- [x] **nano-banana-pro** - `docs/NANO_BANANA_PRO_INTEGRATION.md`
- [x] **bytedance/v1-pro-fast-image-to-video** - `docs/BYTEDANCE_V1_PRO_FAST_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **grok-imagine/image-to-video** - `docs/GROK_IMAGINE_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **grok-imagine/text-to-video** - `docs/GROK_IMAGINE_TEXT_TO_VIDEO_INTEGRATION.md`
- [x] **grok-imagine/text-to-image** - `docs/GROK_IMAGINE_TEXT_TO_IMAGE_INTEGRATION.md`
- [x] **grok-imagine/upscale** - `docs/GROK_IMAGINE_UPSCALE_INTEGRATION.md`
- [x] **hailuo/2-3-image-to-video-pro** - `docs/HAILUO_2_3_IMAGE_TO_VIDEO_PRO_INTEGRATION.md`
- [x] **hailuo/2-3-image-to-video-standard** - `docs/HAILUO_2_3_IMAGE_TO_VIDEO_STANDARD_INTEGRATION.md`
- [x] **topaz/image-upscale** - `docs/TOPAZ_IMAGE_UPSCALE_INTEGRATION.md`
  - Обязательные: `image_url` (string), `upscale_factor` ("1" | "2" | "4" | "8")
  - Default: `image_url="https://static.aiquickdraw.com/tools/example/1762752805607_mErUj1KR.png"`, `upscale_factor="2"`

## 🔍 Проверка соответствия

Каждая модель проверяется на:
1. ✅ Соответствие обязательным параметрам
2. ✅ Соответствие опциональным параметрам
3. ✅ Правильность дефолтных значений
4. ✅ Валидация и нормализация параметров
5. ✅ Обработка ошибок

## 📝 Формат документации

Каждый файл документации содержит:
- Обзор модели
- Ссылки на API документацию
- Параметры запроса (обязательные и опциональные)
- Допустимые значения
- Реализация в коде
- Примеры использования
- Ошибки валидации
- Чеклист интеграции

## ⚠️ Критически важно

1. **Все инструкции фиксируются** - каждая предоставленная документация сохраняется
2. **Строгое соответствие** - интеграция должна точно следовать правилам из документации
3. **Валидация обязательна** - все параметры проверяются согласно документации
4. **Дефолтные значения** - применяются строго как указано в документации

---

**Последнее обновление**: Все модели интегрированы согласно официальной документации KIE AI API.

