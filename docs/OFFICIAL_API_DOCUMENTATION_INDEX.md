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

- [x] **wan/2-5-text-to-video** - `docs/WAN_2_5_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 800 chars)
  - Опциональные: `duration` ("5" | "10"), `aspect_ratio` ("16:9" | "9:16" | "1:1"), `resolution` ("720p" | "1080p"), `negative_prompt` (max 500 chars), `enable_prompt_expansion` (boolean), `seed` (number)
  - Default: `duration="5"`, `aspect_ratio="16:9"`, `resolution="1080p"`, `negative_prompt=""`, `enable_prompt_expansion=true`
  - Важно: `prompt` максимум 800 символов (в 2-6 было 5000)! `duration` только "5" или "10" (в 2-6 есть "15")!
- [x] **wan/2-5-image-to-video** - `docs/WAN_2_5_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 800 chars), `image_url` (string, не массив!)
  - Опциональные: `duration` ("5" | "10"), `resolution` ("720p" | "1080p"), `negative_prompt` (max 500 chars), `enable_prompt_expansion` (boolean), `seed` (number)
  - Default: `image_url="https://file.aiquickdraw.com/..."`, `duration="5"`, `resolution="1080p"`, `negative_prompt=""`, `enable_prompt_expansion=true`
  - Важно: `image_url` - это string, а не массив! `prompt` максимум 800 символов (в 2-6 было 5000)!
- [x] **wan/2-2-animate-move** - `docs/WAN_2_2_ANIMATE_MOVE_INTEGRATION.md`
  - Обязательные: `video_url` (string, не массив!), `image_url` (string)
  - Опциональные: `resolution` ("480p" | "580p" | "720p")
  - Default: `video_url="https://file.aiquickdraw.com/..."`, `image_url="https://file.aiquickdraw.com/..."`, `resolution="480p"`
  - Важно: Требует оба параметра: `video_url` И `image_url`! НЕТ параметра `prompt` и `duration`!
- [x] **wan/2-2-animate-replace** - `docs/WAN_2_2_ANIMATE_REPLACE_INTEGRATION.md`
  - Обязательные: `video_url` (string, не массив!), `image_url` (string)
  - Опциональные: `resolution` ("480p" | "580p" | "720p")
  - Default: `video_url="https://file.aiquickdraw.com/..."`, `image_url="https://file.aiquickdraw.com/..."`, `resolution="480p"`
  - Важно: Требует оба параметра: `video_url` И `image_url`! НЕТ параметра `prompt` и `duration`! Заменяет объекты в видео на основе изображения!
- [x] **wan/2-6-text-to-video** - `docs/WAN_2_6_TEXT_TO_VIDEO_INTEGRATION.md`
- [x] **wan/2-6-image-to-video** - `docs/WAN_2_6_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **wan/2-6-video-to-video** - `docs/WAN_2_6_VIDEO_TO_VIDEO_INTEGRATION.md`

### ✅ Seedream Models

- [x] **seedream/4.5-text-to-image** - `docs/SEEDREAM_4_5_TEXT_TO_IMAGE_INTEGRATION.md`
- [x] **seedream/4.5-edit** - `docs/SEEDREAM_4_5_EDIT_INTEGRATION.md`

### ✅ Kling Models

- [x] **kling-2.6/image-to-video** - `docs/KLING_2_6_IMAGE_TO_VIDEO_INTEGRATION.md`
- [x] **kling-2.6/text-to-video** - `docs/KLING_2_6_TEXT_TO_VIDEO_INTEGRATION.md`
- [x] **kling/v2-5-turbo-text-to-video-pro** - `docs/KLING_V2_5_TURBO_TEXT_TO_VIDEO_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 2500 chars)
  - Опциональные: `duration` ("5" | "10"), `aspect_ratio` ("16:9" | "9:16" | "1:1"), `negative_prompt` (max 2500 chars), `cfg_scale` (0-1, step 0.1)
  - Default: `duration="5"`, `aspect_ratio="16:9"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`
- [x] **kling/v2-5-turbo-image-to-video-pro** - `docs/KLING_V2_5_TURBO_IMAGE_TO_VIDEO_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 2500 chars), `image_url` (string, не массив!)
  - Опциональные: `tail_image_url` (string), `duration` ("5" | "10"), `negative_prompt` (max 2496 chars), `cfg_scale` (0-1, step 0.1)
  - Default: `image_url="https://file.aiquickdraw.com/..."`, `duration="5"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`
  - Важно: `image_url` - это string, а не массив! `negative_prompt` максимум 2496 символов (не 2500)!

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
- [x] **hailuo/02-text-to-video-pro** - `docs/HAILUO_02_TEXT_TO_VIDEO_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 1500 chars)
  - Опциональные: `prompt_optimizer` (boolean)
  - Default: `prompt_optimizer=true`
  - Важно: `prompt` максимум 1500 символов (меньше чем у других моделей)! НЕТ параметров `duration`, `resolution`, `image_url`!
- [x] **hailuo/02-text-to-video-standard** - `docs/HAILUO_02_TEXT_TO_VIDEO_STANDARD_INTEGRATION.md`
  - Обязательные: `prompt` (max 1500 chars)
  - Опциональные: `duration` ("6" | "10"), `prompt_optimizer` (boolean)
  - Default: `duration="6"`, `prompt_optimizer=true`
  - Важно: `prompt` максимум 1500 символов! Есть параметр `duration` (в отличие от pro версии)! НЕТ параметра `resolution`!
- [x] **kling/v1-avatar-standard** - `docs/KLING_V1_AVATAR_STANDARD_INTEGRATION.md`
  - Обязательные: `image_url`, `audio_url`, `prompt` (max 5000 chars)
  - Опциональные: нет
  - Default: нет (все параметры обязательные)
  - Важно: Все три параметра обязательны! Максимальный размер файлов: 10MB для изображения и аудио!
- [x] **hailuo/02-image-to-video-pro** - `docs/HAILUO_02_IMAGE_TO_VIDEO_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 1500 chars), `image_url` (string, не массив!)
  - Опциональные: `end_image_url` (string), `prompt_optimizer` (boolean)
  - Default: `image_url="https://file.aiquickdraw.com/..."`, `prompt_optimizer=true`
  - Важно: `prompt` максимум 1500 символов! `image_url` - это string, а не массив! Есть `end_image_url` для последнего кадра! НЕТ параметров `duration`, `resolution`!
- [x] **hailuo/02-image-to-video-standard** - `docs/HAILUO_02_IMAGE_TO_VIDEO_STANDARD_INTEGRATION.md`
  - Обязательные: `prompt` (max 1500 chars), `image_url` (string, не массив!)
  - Опциональные: `end_image_url` (string, default URL), `duration` ("6" | "10"), `resolution` ("512P" | "768P"), `prompt_optimizer` (boolean)
  - Default: `image_url="https://file.aiquickdraw.com/..."`, `end_image_url="https://file.aiquickdraw.com/..."`, `duration="10"`, `resolution="768P"`, `prompt_optimizer=true`
  - Важно: `prompt` максимум 1500 символов! Есть `duration` и `resolution` (в отличие от pro версии)! `end_image_url` имеет default значение!
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

