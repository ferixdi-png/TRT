# 📚 Индекс официальной документации KIE AI API

> **ВАЖНО**: Все инструкции в этом файле являются официальными правилами генерации. Интеграция должна строго следовать этим правилам "по гарантии по закону".

## 🚨 КРИТИЧЕСКИ ВАЖНО: СТРОГИЕ ПРАВИЛА ИНТЕГРАЦИИ

**ВСЕ модели ДОЛЖНЫ работать СТРОГО согласно предоставленной документации API.**

**НИКАКИХ отклонений, НИКАКИХ предположений, НИКАКИХ "улучшений" без явного указания пользователя.**

📋 **Подробные правила:** [`docs/STRICT_INTEGRATION_RULES.md`](STRICT_INTEGRATION_RULES.md)

**Основные принципы:**
- ✅ Все обязательные параметры — ДОЛЖНЫ быть обязательными в валидации
- ✅ Все опциональные параметры — ДОЛЖНЫ быть опциональными
- ✅ Все ограничения (длина, диапазоны, enum) — ДОЛЖНЫ быть проверены
- ✅ Все дефолтные значения — ДОЛЖНЫ быть установлены согласно документации
- ✅ Типы данных — ДОЛЖНЫ соответствовать документации
- ❌ НЕ добавлять параметры, которых нет в документации
- ❌ НЕ изменять типы данных
- ❌ НЕ игнорировать ограничения
- ❌ НЕ устанавливать произвольные дефолты

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
- [x] **kling/ai-avatar-v1-pro** - `docs/KLING_AI_AVATAR_V1_PRO_INTEGRATION.md`
  - Обязательные: `image_url`, `audio_url`, `prompt` (max 5000 chars)
  - Опциональные: нет
  - Default: нет (все параметры обязательные)
  - Важно: Все три параметра обязательны! Pro версия модели! Параметры идентичны kling/v1-avatar-standard!
- [x] **bytedance/seedream-v4-text-to-image** - `docs/BYTEDANCE_SEEDREAM_V4_TEXT_TO_IMAGE_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000 chars)
  - Опциональные: `image_size` (enum, 9 значений), `image_resolution` ("1K" | "2K" | "4K"), `max_images` (1-6), `seed` (number)
  - Default: `image_size="square_hd"`, `image_resolution="1K"`, `max_images=1`
  - Важно: Уникальные параметры! Использует `image_size` и `image_resolution` вместо стандартных `width/height`! Финальное разрешение = `image_size` + `image_resolution`!
- [x] **bytedance/seedream-v4-edit** - `docs/BYTEDANCE_SEEDREAM_V4_EDIT_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000 chars), `image_urls` (array, до 10 изображений)
  - Опциональные: `image_size` (enum, 9 значений), `image_resolution` ("1K" | "2K" | "4K"), `max_images` (1-6), `seed` (number)
  - Default: `image_size="square_hd"`, `image_resolution="1K"`, `max_images=1`
  - Важно: Уникальные параметры! Использует `image_urls` (массив, до 10) вместо стандартного `image_url`! Использует `image_size` и `image_resolution` вместо стандартных `width/height`! Финальное разрешение = `image_size` + `image_resolution`!
- [x] **infinitalk/from-audio** - `docs/INFINITALK_FROM_AUDIO_INTEGRATION.md`
  - Обязательные: `image_url`, `audio_url`, `prompt` (max 5000 chars)
  - Опциональные: `resolution` ("480p" | "720p"), `seed` (number, 10000-1000000)
  - Default: `resolution="480p"`
  - Важно: Все три параметра обязательны! `prompt` обязательный (в отличие от других lip sync моделей)! `seed` с ограничением: только 10000-1000000!
- [x] **recraft/remove-background** - `docs/RECRAFT_REMOVE_BACKGROUND_INTEGRATION.md`
  - Обязательные: `image` (string, макс 5MB, PNG/JPG/WEBP, макс 16MP, макс 4096px, мин 256px)
  - Опциональные: нет
  - Default: нет (параметр обязательный)
  - Важно: Параметр называется `image` (не `image_url`)! Более строгие ограничения: макс 5MB (вместо 10MB), макс 16MP, макс 4096px, мин 256px! `image_url` или `image_base64` автоматически нормализуются в `image`!
- [x] **recraft/crisp-upscale** - `docs/RECRAFT_CRISP_UPSCALE_INTEGRATION.md`
  - Обязательные: `image` (string, макс 10MB, PNG/JPG/WEBP)
  - Опциональные: нет
  - Default: нет (параметр обязательный)
  - Важно: Параметр называется `image` (не `image_url`)! Только один параметр - нет scale, upscale_factor и т.д.! `image_url` или `image_base64` автоматически нормализуются в `image`!
- [x] **ideogram/v3-reframe** - `docs/IDEOGRAM_V3_REFrame_INTEGRATION.md`
  - Обязательные: `image_url`, `image_size` (enum, 6 значений)
  - Опциональные: `rendering_speed` ("TURBO" | "BALANCED" | "QUALITY"), `style` ("AUTO" | "GENERAL" | "REALISTIC" | "DESIGN"), `num_images` ("1" | "2" | "3" | "4"), `seed` (number)
  - Default: `image_size="square_hd"`, `rendering_speed="BALANCED"`, `style="AUTO"`, `num_images="1"`, `seed=0`
- [x] **ideogram/character-edit** - `docs/IDEOGRAM_CHARACTER_EDIT_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp), `mask_url` (max 10MB, jpeg/png/webp), `reference_image_urls` (массив, max 10MB общий размер, jpeg/png/webp, только 1 поддерживается)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY), `style` (enum: AUTO/REALISTIC/FICTION), `expand_prompt` (boolean), `num_images` (string enum: 1/2/3/4), `seed`
  - Default: `rendering_speed="BALANCED"`, `style="AUTO"`, `expand_prompt=true`, `num_images="1"`
  - Важно: Модель для редактирования персонажей с inpainting! Использует `mask_url` для указания области для inpainting! Использует `reference_image_urls` для указания референсов персонажа (только 1 изображение поддерживается, остальные игнорируются)! Уникальные параметры: `mask_url`, `reference_image_urls`, `expand_prompt`! НЕТ параметров `strength`, `negative_prompt`, `width`, `height`, `steps`, `guidance`!
- [x] **ideogram/character-remix** - `docs/IDEOGRAM_CHARACTER_REMIX_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp), `reference_image_urls` (массив, max 10MB общий размер, jpeg/png/webp, только 1 поддерживается)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY), `style` (enum: AUTO/REALISTIC/FICTION), `expand_prompt` (boolean), `image_size` (enum, 6 значений), `num_images` (string enum: 1/2/3/4), `seed`, `strength` (0.1-1), `negative_prompt` (max 500), `image_urls` (массив, max 10MB общий размер, jpeg/png/webp), `reference_mask_urls` (string, max 10MB, jpeg/png/webp)
  - Default: `rendering_speed="BALANCED"`, `style="AUTO"`, `expand_prompt=true`, `image_size="square_hd"`, `num_images="1"`, `strength=0.8`, `negative_prompt=""`, `image_urls=[]`, `reference_mask_urls=""`
  - Важно: Модель для ремикса персонажей! Использует `reference_image_urls` для указания референсов персонажа (только 1 изображение поддерживается, остальные игнорируются)! Использует `image_size` вместо стандартных `width`/`height`! Уникальные параметры: `strength`, `negative_prompt`, `image_urls`, `reference_mask_urls`! НЕТ параметра `mask_url` (есть в ideogram/character-edit)!
- [x] **ideogram/character** - `docs/IDEOGRAM_CHARACTER_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `reference_image_urls` (массив, max 10MB общий размер, jpeg/png/webp, только 1 поддерживается)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY), `style` (enum: AUTO/REALISTIC/FICTION), `expand_prompt` (boolean), `num_images` (string enum: 1/2/3/4), `image_size` (enum, 6 значений), `seed`, `negative_prompt` (max 5000!)
  - Default: `rendering_speed="BALANCED"`, `style="AUTO"`, `expand_prompt=true`, `num_images="1"`, `image_size="square_hd"`, `negative_prompt=""`
  - Важно: Модель для генерации персонажей из текста с character reference! Использует `reference_image_urls` для указания референсов персонажа (только 1 изображение поддерживается, остальные игнорируются)! Использует `image_size` вместо стандартных `width`/`height`! Уникальные параметры: `reference_image_urls`, `rendering_speed`, `expand_prompt`, `num_images`! `negative_prompt` имеет максимум 5000 символов (не 500!)! НЕТ параметров `image_url`, `width`, `height`, `steps`, `guidance`, `guidance_scale`!
- [x] **bytedance/v1-lite-text-to-video** - `docs/BYTEDANCE_V1_LITE_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000)
  - Опциональные: `aspect_ratio` (enum, 6 значений), `resolution` (enum: 480p/720p/1080p), `duration` (enum: "5"/"10"), `camera_fixed` (boolean), `seed` (может быть -1), `enable_safety_checker` (boolean)
  - Default: `aspect_ratio="16:9"`, `resolution="720p"`, `duration="5"`, `camera_fixed=false`, `enable_safety_checker=true`
  - Важно: Модель для генерации видео из текста! Использует `camera_fixed` для управления позицией камеры (уникальный параметр)! Использует `duration` как string enum ("5" или "10")! `seed` может быть -1 для случайного seed! `prompt` имеет максимум 10000 символов (больше, чем у большинства других моделей)! НЕТ параметров `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`!
- [x] **bytedance/v1-pro-text-to-video** - `docs/BYTEDANCE_V1_PRO_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000)
  - Опциональные: `aspect_ratio` (enum, 6 значений, включает 21:9), `resolution` (enum: 480p/720p/1080p), `duration` (enum: "5"/"10"), `camera_fixed` (boolean), `seed` (может быть -1, default -1), `enable_safety_checker` (boolean)
  - Default: `aspect_ratio="16:9"`, `resolution="720p"`, `duration="5"`, `camera_fixed=false`, `seed=-1`, `enable_safety_checker=true`
  - Важно: Модель для генерации видео из текста - Pro версия! Использует `camera_fixed` для управления позицией камеры (уникальный параметр)! Использует `duration` как string enum ("5" или "10")! `seed` может быть -1 для случайного seed, default -1! `aspect_ratio` включает "21:9" (6 значений, в отличие от v1-lite)! `prompt` имеет максимум 10000 символов (больше, чем у большинства других моделей)! НЕТ параметров `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`!
- [x] **bytedance/v1-lite-image-to-video** - `docs/BYTEDANCE_V1_LITE_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `resolution` (enum: 480p/720p/1080p), `duration` (enum: "5"/"10"), `camera_fixed` (boolean), `seed` (может быть -1, default -1), `enable_safety_checker` (boolean), `end_image_url` (string, max 10MB, jpeg/png/webp, default "")
  - Default: `resolution="720p"`, `duration="5"`, `camera_fixed=false`, `seed=-1`, `enable_safety_checker=true`, `end_image_url=""`
  - Важно: Модель для генерации видео из изображения! Использует `camera_fixed` для управления позицией камеры (уникальный параметр)! Использует `duration` как string enum ("5" или "10")! Использует `end_image_url` для указания изображения, которым заканчивается видео (уникальный параметр)! `seed` может быть -1 для случайного seed, default -1! `prompt` имеет максимум 10000 символов (больше, чем у большинства других моделей)! НЕТ параметров `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`, `strength`!
- [x] **bytedance/v1-pro-image-to-video** - `docs/BYTEDANCE_V1_PRO_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `resolution` (enum: 480p/720p/1080p), `duration` (enum: "5"/"10"), `camera_fixed` (boolean), `seed` (может быть -1, default -1), `enable_safety_checker` (boolean)
  - Default: `resolution="720p"`, `duration="5"`, `camera_fixed=false`, `seed=-1`, `enable_safety_checker=true`
  - Важно: Модель для генерации видео из изображения - Pro версия! Использует `camera_fixed` для управления позицией камеры (уникальный параметр)! Использует `duration` как string enum ("5" или "10")! НЕТ параметра `end_image_url` (есть в v1-lite-image-to-video)! `seed` может быть -1 для случайного seed, default -1! `prompt` имеет максимум 10000 символов (больше, чем у большинства других моделей)! НЕТ параметров `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`, `strength`!
- [x] **bytedance/v1-pro-fast-image-to-video** - `docs/BYTEDANCE_V1_PRO_FAST_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `resolution` (enum: 720p/1080p, НЕТ 480p!), `duration` (enum: "5"/"10")
  - Default: `resolution="720p"`, `duration="5"`
  - Важно: Модель для генерации видео из изображения - Pro Fast версия! Использует `duration` как string enum ("5" или "10")! `resolution` только 2 значения (720p, 1080p), НЕТ 480p (в отличие от других v1 моделей)! НЕТ параметров `camera_fixed`, `seed`, `enable_safety_checker`, `end_image_url` (есть в других v1 моделях)! `prompt` имеет максимум 10000 символов (больше, чем у большинства других моделей)! НЕТ параметров `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`, `strength`!
- [x] **kling/v2-1-master-image-to-video** - `docs/KLING_V2_1_MASTER_IMAGE_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `duration` (enum: "5"/"10"), `negative_prompt` (max 500, default "blur, distort, and low quality"), `cfg_scale` (0-1, шаг 0.1, default 0.5)
  - Default: `duration="5"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`
  - Важно: Модель для генерации видео из изображения - Master версия! Использует `duration` как string enum ("5" или "10")! Использует `cfg_scale` для управления следованием промпту (диапазон 0-1, шаг 0.1, default 0.5)! `negative_prompt` имеет default "blur, distort, and low quality" (не пустая строка!)! `prompt` имеет максимум 5000 символов! НЕТ параметров `resolution`, `camera_fixed`, `seed`, `enable_safety_checker`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `motion`, `style`, `strength`!
- [x] **kling/v2-1-standard** - `docs/KLING_V2_1_STANDARD_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `duration` (enum: "5"/"10"), `negative_prompt` (max 500, default "blur, distort, and low quality"), `cfg_scale` (0-1, шаг 0.1, default 0.5)
  - Default: `duration="5"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`
  - Важно: Модель для генерации видео из изображения - Standard версия! Использует `duration` как string enum ("5" или "10")! Использует `cfg_scale` для управления следованием промпту (диапазон 0-1, шаг 0.1, default 0.5)! `negative_prompt` имеет default "blur, distort, and low quality" (не пустая строка!)! `prompt` имеет максимум 5000 символов! НЕТ параметров `resolution`, `camera_fixed`, `seed`, `enable_safety_checker`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `motion`, `style`, `strength`! Идентична kling/v2-1-master-image-to-video по параметрам, но это Standard версия!
- [x] **kling/v2-1-pro** - `docs/KLING_V2_1_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `duration` (enum: "5"/"10"), `negative_prompt` (max 500, default "blur, distort, and low quality"), `cfg_scale` (0-1, шаг 0.1, default 0.5), `tail_image_url` (max 10MB, jpeg/png/webp, default "")
  - Default: `duration="5"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`, `tail_image_url=""`
  - Важно: Модель для генерации видео из изображения - Pro версия! Использует `duration` как string enum ("5" или "10")! Использует `cfg_scale` для управления следованием промпту (диапазон 0-1, шаг 0.1, default 0.5)! `negative_prompt` имеет default "blur, distort, and low quality" (не пустая строка!)! `tail_image_url` имеет default "" (пустая строка!) - уникальный параметр для Pro версии! `prompt` имеет максимум 5000 символов! НЕТ параметров `resolution`, `camera_fixed`, `seed`, `enable_safety_checker`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `motion`, `style`, `strength`! Отличается от kling/v2-1-standard и kling/v2-1-master-image-to-video наличием параметра `tail_image_url`!
- [x] **kling/v2-1-master-text-to-video** - `docs/KLING_V2_1_MASTER_TEXT_TO_VIDEO_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `duration` (enum: "5"/"10"), `aspect_ratio` (enum: "16:9"/"9:16"/"1:1"), `negative_prompt` (max 500, default "blur, distort, and low quality"), `cfg_scale` (0-1, шаг 0.1, default 0.5)
  - Default: `duration="5"`, `aspect_ratio="16:9"`, `negative_prompt="blur, distort, and low quality"`, `cfg_scale=0.5`
  - Важно: Модель для генерации видео из текста - Master версия! Использует `duration` как string enum ("5" или "10")! Использует `aspect_ratio` для управления соотношением сторон (enum: "16:9", "9:16", "1:1", default "16:9")! Использует `cfg_scale` для управления следованием промпту (диапазон 0-1, шаг 0.1, default 0.5)! `negative_prompt` имеет default "blur, distort, and low quality" (не пустая строка!)! `prompt` имеет максимум 5000 символов! НЕТ параметров `image_url`, `tail_image_url`, `resolution`, `camera_fixed`, `seed`, `enable_safety_checker`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `motion`, `style`, `strength`! Отличается от kling/v2-1-master-image-to-video тем, что это text-to-video (нет image_url), но есть aspect_ratio!
- [x] **ideogram/v3-text-to-image** - `docs/IDEOGRAM_V3_TEXT_TO_IMAGE_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY, default "BALANCED"), `style` (enum: AUTO/GENERAL/REALISTIC/DESIGN, default "AUTO"), `expand_prompt` (boolean, default true), `image_size` (enum, 6 значений, default "square_hd"), `seed` (number), `negative_prompt` (max 5000, default "")
  - Default: `rendering_speed="BALANCED"`, `style="AUTO"`, `expand_prompt=true`, `image_size="square_hd"`, `negative_prompt=""`
  - Важно: Модель для генерации изображений из текста - V3 версия! Использует `rendering_speed` для управления скоростью рендеринга (enum: TURBO/BALANCED/QUALITY, default BALANCED)! Использует `style` для управления типом стиля (enum: AUTO/GENERAL/REALISTIC/DESIGN, default AUTO)! Не может использоваться вместе с style_codes! Использует `expand_prompt` для управления MagicPrompt (boolean, default true)! Использует `image_size` для управления разрешением (enum, 6 значений, default square_hd)! `negative_prompt` имеет максимум 5000 символов (больше, чем у большинства других моделей!) и default "" (пустая строка!)! `prompt` имеет максимум 5000 символов! НЕТ параметров `reference_image_urls`, `num_images` (есть в ideogram/character)!
- [x] **ideogram/v3-edit** - `docs/IDEOGRAM_V3_EDIT_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp), `mask_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY, default "BALANCED"), `expand_prompt` (boolean, default true), `seed` (number)
  - Default: `rendering_speed="BALANCED"`, `expand_prompt=true`
  - Важно: Модель для редактирования изображений с использованием маски (inpainting) - V3 версия! Использует `mask_url` для указания маски для инпейнтинга (обязательный параметр!) - уникальный параметр для inpainting! Использует `rendering_speed` для управления скоростью рендеринга (enum: TURBO/BALANCED/QUALITY, default BALANCED)! Использует `expand_prompt` для управления MagicPrompt (boolean, default true)! `prompt` имеет максимум 5000 символов! НЕТ параметров `style`, `image_size`, `negative_prompt`, `num_images` (есть в других ideogram v3 моделях)! Отличается от ideogram/v3-text-to-image наличием обязательных `image_url` и `mask_url` (для inpainting)!
- [x] **ideogram/v3-remix** - `docs/IDEOGRAM_V3_REMIX_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `rendering_speed` (enum: TURBO/BALANCED/QUALITY, default "BALANCED"), `style` (enum: AUTO/GENERAL/REALISTIC/DESIGN, default "AUTO"), `expand_prompt` (boolean, default true), `image_size` (enum, 6 значений, default "square_hd"), `num_images` (enum: "1"/"2"/"3"/"4", default "1"), `seed` (number), `strength` (0.01-1, шаг 0.01, default 0.8), `negative_prompt` (max 5000, default "")
  - Default: `rendering_speed="BALANCED"`, `style="AUTO"`, `expand_prompt=true`, `image_size="square_hd"`, `num_images="1"`, `strength=0.8`, `negative_prompt=""`
  - Важно: Модель для ремикса изображений - V3 версия! Использует `rendering_speed` для управления скоростью рендеринга (enum: TURBO/BALANCED/QUALITY, default BALANCED)! Использует `style` для управления типом стиля (enum: AUTO/GENERAL/REALISTIC/DESIGN, default AUTO)! Не может использоваться вместе с style_codes! Использует `expand_prompt` для управления MagicPrompt (boolean, default true)! Использует `image_size` для управления разрешением (enum, 6 значений, default square_hd)! Использует `num_images` для управления количеством изображений (string enum: "1", "2", "3", "4", default "1")! Использует `strength` для управления силой входного изображения (number, диапазон 0.01-1, шаг 0.01, default 0.8)! `negative_prompt` имеет максимум 5000 символов (больше, чем у большинства других моделей!) и default "" (пустая строка!)! `prompt` имеет максимум 5000 символов! НЕТ параметра `mask_url` (есть в ideogram/v3-edit)! Отличается от ideogram/v3-text-to-image наличием обязательного `image_url` и параметров `num_images`, `strength`!
- [x] **wan/2-2-a14b-text-to-video-turbo** - `docs/WAN_2_2_A14B_TEXT_TO_VIDEO_TURBO_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `resolution` (enum: 480p/580p/720p, default "720p"), `aspect_ratio` (enum: 16:9/9:16/1:1, default "16:9"), `enable_prompt_expansion` (boolean, default false), `seed` (0-2147483647, default 0), `acceleration` (enum: none/regular, default "none")
  - Default: `resolution="720p"`, `aspect_ratio="16:9"`, `enable_prompt_expansion=false`, `seed=0`, `acceleration="none"`
  - Важно: Модель для генерации видео из текста - Turbo версия с A14b! Использует `resolution` для управления разрешением (enum: 480p/580p/720p, default 720p)! ВАЖНО: Включает 580p (уникальное значение, которого нет в других wan моделях)! Использует `aspect_ratio` для управления соотношением сторон (enum: 16:9/9:16/1:1, default 16:9)! ВАЖНО: Включает 1:1 (которого нет в wan/2-2-a14b-speech-to-video-turbo)! Использует `enable_prompt_expansion` для управления расширением промпта (boolean, default false)! Использует `seed` для управления воспроизводимостью (number, диапазон 0-2147483647, default 0)! Использует `acceleration` для управления уровнем ускорения (enum: none/regular, default none)! `prompt` имеет максимум 5000 символов! НЕТ параметров `duration`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `cfg_scale`! Отличается от wan/2-2-a14b-speech-to-video-turbo тем, что это text-to-video (нет audio_url), но есть enable_prompt_expansion и acceleration!
- [x] **wan/2-2-a14b-image-to-video-turbo** - `docs/WAN_2_2_A14B_IMAGE_TO_VIDEO_TURBO_INTEGRATION.md`
  - Обязательные: `image_url` (max 10MB, jpeg/png/webp), `prompt` (max 5000)
  - Опциональные: `resolution` (enum: 480p/580p/720p, default "720p"), `aspect_ratio` (enum: auto/16:9/9:16/1:1, default "auto"), `enable_prompt_expansion` (boolean, default false), `seed` (0-2147483647, default 0), `acceleration` (enum: none/regular, default "none")
  - Default: `resolution="720p"`, `aspect_ratio="auto"`, `enable_prompt_expansion=false`, `seed=0`, `acceleration="none"`
  - Важно: Модель для генерации видео из изображения - Turbo версия с A14b! Использует `image_url` для указания входного изображения (обязательный параметр!) - если входное изображение не соответствует выбранному соотношению сторон, оно изменяется и обрезается по центру! Использует `prompt` для управления генерацией видео (обязательный параметр, максимум 5000 символов)! Использует `resolution` для управления разрешением (enum: 480p/580p/720p, default 720p)! ВАЖНО: Включает 580p (уникальное значение, которого нет в других wan моделях)! Использует `aspect_ratio` для управления соотношением сторон (enum: auto/16:9/9:16/1:1, default auto)! ВАЖНО: Включает "auto" (которого нет в wan/2-2-a14b-text-to-video-turbo)! Если 'auto', соотношение сторон будет определено автоматически на основе входного изображения! Использует `enable_prompt_expansion` для управления расширением промпта (boolean, default false)! Использует `seed` для управления воспроизводимостью (number, диапазон 0-2147483647, default 0)! Использует `acceleration` для управления уровнем ускорения (enum: none/regular, default none)! `prompt` имеет максимум 5000 символов! НЕТ параметров `duration`, `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `cfg_scale`, `strength`! Отличается от wan/2-2-a14b-text-to-video-turbo тем, что это image-to-video (есть обязательный image_url), и aspect_ratio имеет default "auto" (вместо "16:9")!
- [x] **google/imagen4-fast** - `docs/GOOGLE_IMAGEN4_FAST_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `negative_prompt` (max 5000, default ""), `aspect_ratio` (enum: 1:1/16:9/9:16/3:4/4:3, default "16:9"), `num_images` (enum: "1"/"2"/"3"/"4", default "1"), `seed` (number)
  - Default: `negative_prompt=""`, `aspect_ratio="16:9"`, `num_images="1"`
  - Важно: Модель для генерации изображений из текста - Fast версия Imagen4! Использует `prompt` для управления генерацией (обязательный параметр, максимум 5000 символов)! Использует `negative_prompt` для управления тем, что следует избегать (опциональный параметр, максимум 5000 символов, default "")! Использует `aspect_ratio` для управления соотношением сторон (enum: 1:1/16:9/9:16/3:4/4:3, default 16:9)! ВАЖНО: Включает 3:4 и 4:3 (которых нет в google/nano-banana)! Использует `num_images` для управления количеством изображений (string enum: "1", "2", "3", "4", default "1")! Использует `seed` для управления воспроизводимостью (number)! `prompt` имеет максимум 5000 символов! `negative_prompt` имеет максимум 5000 символов и default "" (пустая строка!)! НЕТ параметров `width`, `height`, `guidance`, `steps`, `style`, `output_format`, `image_size`! Отличается от google/nano-banana наличием `num_images` и более широким набором значений `aspect_ratio` (включает 3:4 и 4:3)!
- [x] **google/imagen4-ultra** - `docs/GOOGLE_IMAGEN4_ULTRA_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `negative_prompt` (max 5000, default ""), `aspect_ratio` (enum: 1:1/16:9/9:16/3:4/4:3, default "1:1"), `seed` (string, max 500, default "")
  - Default: `negative_prompt=""`, `aspect_ratio="1:1"`, `seed=""`
  - Важно: Модель для генерации изображений из текста - Ultra версия Imagen4! Использует `prompt` для управления генерацией (обязательный параметр, максимум 5000 символов)! Использует `negative_prompt` для управления тем, что следует избегать (опциональный параметр, максимум 5000 символов, default "")! Использует `aspect_ratio` для управления соотношением сторон (enum: 1:1/16:9/9:16/3:4/4:3, default 1:1)! ВАЖНО: Default "1:1" (а не "16:9" как в imagen4-fast)! Использует `seed` для управления воспроизводимостью (string, максимум 500 символов, default "")! ВАЖНО: seed здесь - это string, а не number (как в других моделях)! `prompt` имеет максимум 5000 символов! `negative_prompt` имеет максимум 5000 символов и default "" (пустая строка!)! НЕТ параметра `num_images` (который есть в imagen4-fast)! НЕТ параметров `width`, `height`, `guidance`, `steps`, `style`, `output_format`, `image_size`! Отличается от google/imagen4-fast тем, что `aspect_ratio` имеет default "1:1" (вместо "16:9"), `seed` - это string (а не number), и НЕТ параметра `num_images`!
- [x] **google/imagen4** - `docs/GOOGLE_IMAGEN4_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `negative_prompt` (max 5000, default ""), `aspect_ratio` (enum: 1:1/16:9/9:16/3:4/4:3, default "1:1"), `num_images` (enum: "1"/"2"/"3"/"4", default "1"), `seed` (string, max 500, default "")
  - Default: `negative_prompt=""`, `aspect_ratio="1:1"`, `num_images="1"`, `seed=""`
  - Важно: Модель для генерации изображений из текста - базовая версия Imagen4! Использует `prompt` для управления генерацией (обязательный параметр, максимум 5000 символов)! Использует `negative_prompt` для управления тем, что следует избегать (опциональный параметр, максимум 5000 символов, default "")! Использует `aspect_ratio` для управления соотношением сторон (enum: 1:1/16:9/9:16/3:4/4:3, default 1:1)! ВАЖНО: Default "1:1" (как в ultra, а не "16:9" как в fast)! Использует `num_images` для управления количеством изображений (string enum: "1", "2", "3", "4", default "1")! ВАЖНО: Есть num_images (как в fast, но не в ultra)! Использует `seed` для управления воспроизводимостью (string, максимум 500 символов, default "")! ВАЖНО: seed здесь - это string, а не number (как в ultra, а не как в fast)! `prompt` имеет максимум 5000 символов! `negative_prompt` имеет максимум 5000 символов и default "" (пустая строка!)! НЕТ параметров `width`, `height`, `guidance`, `steps`, `style`, `output_format`, `image_size`! Комбинация параметров: имеет `num_images` из fast, но `seed` как string и `aspect_ratio` default "1:1" из ultra!
  - Важно: `image_size` обязательный (в отличие от других моделей)! НЕТ параметра `prompt`! `num_images` - string (не number)!
- [x] **elevenlabs/audio-isolation** - `docs/ELEVENLABS_AUDIO_ISOLATION_INTEGRATION.md`
  - Обязательные: `audio_url` (string, макс 10MB, mpeg/wav/aac/mp4/ogg)
  - Опциональные: нет
  - Default: нет (параметр обязательный)
  - Важно: Только один параметр - `audio_url`! НЕТ дополнительных параметров (mode, strength и т.д.)! `audio` автоматически нормализуется в `audio_url`!
- [x] **elevenlabs/sound-effect-v2** - `docs/ELEVENLABS_SOUND_EFFECT_V2_INTEGRATION.md`
  - Обязательные: `text` (max 5000 chars)
  - Опциональные: `loop` (boolean), `duration_seconds` (0.5-22), `prompt_influence` (0-1), `output_format` (enum, 18 значений)
  - Default: `loop=false`, `prompt_influence=0.3`, `output_format="mp3_44100_128"`
  - Важно: Параметр называется `text` (не `prompt`)! Использует `duration_seconds` вместо `duration`! Уникальные параметры: `loop`, `prompt_influence`, `output_format`! НЕТ параметров `style` и `seed`!
- [x] **elevenlabs/speech-to-text** - `docs/ELEVENLABS_SPEECH_TO_TEXT_INTEGRATION.md`
  - Обязательные: `audio_url` (string, макс 200MB, mpeg/wav/aac/mp4/ogg)
  - Опциональные: `language_code` (string, макс 500), `tag_audio_events` (boolean), `diarize` (boolean)
  - Default: `language_code=""`, `tag_audio_events=true`, `diarize=true`
  - Важно: Использует `language_code` вместо стандартного `language`! Уникальные параметры: `tag_audio_events`, `diarize`! НЕТ параметров `model` и `format`! Максимальный размер файла: 200MB!
- [x] **elevenlabs/text-to-speech-multilingual-v2** - `docs/ELEVENLABS_TEXT_TO_SPEECH_MULTILINGUAL_V2_INTEGRATION.md`
  - Обязательные: `text` (max 5000 chars)
  - Опциональные: `voice` (enum, 21 значение), `stability` (0-1), `similarity_boost` (0-1), `style` (0-1), `speed` (0.7-1.2), `timestamps` (boolean), `previous_text` (max 5000), `next_text` (max 5000), `language_code` (max 500)
  - Default: `voice="Rachel"`, `stability=0.5`, `similarity_boost=0.75`, `style=0`, `speed=1`, `timestamps=false`, `previous_text=""`, `next_text=""`, `language_code=""`
  - Важно: Уникальные параметры: `stability`, `similarity_boost`, `timestamps`, `previous_text`, `next_text`! Использует `language_code` вместо стандартного `language`! НЕТ параметров `model` и `emotion`!
- [x] **wan/2-2-a14b-speech-to-video-turbo** - `docs/WAN_2_2_A14B_SPEECH_TO_VIDEO_TURBO_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp), `audio_url` (max 10MB, mp3/wav/ogg/m4a/flac/aac/x-ms-wma/mpeg)
  - Опциональные: `num_frames` (40-120, кратно 4), `frames_per_second` (4-60), `resolution` (enum: 480p/580p/720p), `negative_prompt` (max 500), `seed`, `num_inference_steps` (2-40), `guidance_scale` (1-10), `shift` (1-10), `enable_safety_checker` (boolean)
  - Default: `num_frames=80`, `frames_per_second=16`, `resolution="480p"`, `negative_prompt=""`, `num_inference_steps=27`, `guidance_scale=3.5`, `shift=5`, `enable_safety_checker=true`
  - Важно: ТРИ обязательных параметра: `prompt`, `image_url`, `audio_url`! Использует `num_frames` вместо стандартного `duration`! Уникальные параметры: `num_inference_steps`, `guidance_scale`, `shift`, `enable_safety_checker`! НЕТ параметров `duration`, `with_audio`, `aspect_ratio`!
- [x] **bytedance/seedream** - `docs/BYTEDANCE_SEEDREAM_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `image_size` (enum, 6 значений), `guidance_scale` (1-10), `seed`, `enable_safety_checker` (boolean)
  - Default: `image_size="square_hd"`, `guidance_scale=2.5`, `enable_safety_checker=true`
  - Важно: Использует `guidance_scale` вместо стандартного `guidance`! Использует `image_size` вместо стандартных `width`/`height`! Уникальный параметр: `enable_safety_checker`! НЕТ параметров `negative_prompt`, `width`, `height`, `steps`, `guidance`, `style`!
- [x] **qwen/image-to-image** - `docs/QWEN_IMAGE_TO_IMAGE_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `strength` (0-1), `output_format` (enum: png/jpeg), `acceleration` (enum: none/regular/high), `negative_prompt` (max 500), `seed`, `num_inference_steps` (2-250), `guidance_scale` (0-20), `enable_safety_checker` (boolean)
  - Default: `strength=0.8`, `output_format="png"`, `acceleration="none"`, `negative_prompt="blurry, ugly"`, `num_inference_steps=30`, `guidance_scale=2.5`, `enable_safety_checker=true`
  - Важно: Использует `num_inference_steps` вместо стандартного `steps`! Использует `guidance_scale` вместо стандартного `guidance`! Уникальные параметры: `output_format`, `acceleration`, `enable_safety_checker`! НЕТ параметров `width`, `height`, `steps`, `guidance`, `style`!
- [x] **qwen/image-edit** - `docs/QWEN_IMAGE_EDIT_INTEGRATION.md`
  - Обязательные: `prompt` (max 2000), `image_url` (max 10MB, jpeg/png/webp)
  - Опциональные: `acceleration` (enum: none/regular/high), `image_size` (enum, 6 значений), `num_inference_steps` (2-49), `seed`, `guidance_scale` (0-20), `sync_mode` (boolean), `num_images` (string enum: 1/2/3/4), `enable_safety_checker` (boolean), `output_format` (enum: png/jpeg), `negative_prompt` (max 500)
  - Default: `acceleration="none"`, `image_size="landscape_4_3"`, `num_inference_steps=25`, `guidance_scale=4`, `sync_mode=false`, `enable_safety_checker=true`, `output_format="png"`, `negative_prompt="blurry, ugly"`
  - Важно: `prompt` имеет максимум 2000 символов (меньше чем у qwen/image-to-image, где 5000)! `num_inference_steps` имеет диапазон 2-49 и default 25 (меньше чем у qwen/image-to-image, где 2-250 и default 30)! `guidance_scale` имеет default 4 (больше чем у qwen/image-to-image, где default 2.5)! Использует `image_size` вместо стандартных `width`/`height`! Уникальные параметры: `sync_mode` (boolean), `num_images` (string enum)! НЕТ параметра `strength` (есть в qwen/image-to-image)!
- [x] **qwen/text-to-image** - `docs/QWEN_TEXT_TO_IMAGE_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `image_size` (enum, 6 значений), `num_inference_steps` (2-250), `seed`, `guidance_scale` (0-20), `enable_safety_checker` (boolean), `output_format` (enum: png/jpeg), `negative_prompt` (max 500), `acceleration` (enum: none/regular/high)
  - Default: `image_size="square_hd"`, `num_inference_steps=30`, `guidance_scale=2.5`, `enable_safety_checker=true`, `output_format="png"`, `negative_prompt=" "` (пробел!), `acceleration="none"`
  - Важно: Использует `num_inference_steps` вместо стандартного `steps`! Использует `guidance_scale` вместо стандартного `guidance`! Использует `image_size` вместо стандартных `width`/`height`! Уникальные параметры: `output_format`, `acceleration`, `enable_safety_checker`! `negative_prompt` имеет default `" "` (пробел!), а не пустую строку! НЕТ параметров `width`, `height`, `steps`, `guidance`, `style`!
- [x] **google/nano-banana** - `docs/GOOGLE_NANO_BANANA_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000)
  - Опциональные: `output_format` (enum: png/jpeg), `image_size` (enum, 11 значений)
  - Default: `output_format="png"`, `image_size="1:1"`
  - Важно: Использует `image_size` вместо стандартных `width`/`height`! Уникальный параметр: `output_format`! НЕТ параметров `negative_prompt`, `width`, `height`, `steps`, `seed`, `guidance`, `guidance_scale`, `style`!
- [x] **google/nano-banana-edit** - `docs/GOOGLE_NANO_BANANA_EDIT_INTEGRATION.md`
  - Обязательные: `prompt` (max 5000), `image_urls` (массив, до 10 изображений, max 10MB каждое, jpeg/png/webp)
  - Опциональные: `output_format` (enum: png/jpeg), `image_size` (enum, 11 значений)
  - Default: `output_format="png"`, `image_size="1:1"`
  - Важно: Использует `image_urls` (массив, до 10) вместо стандартного `image_url`! Использует `image_size` вместо стандартных `width`/`height`! Уникальный параметр: `output_format`! Нормализует `image_url` в `image_urls`! НЕТ параметров `strength`, `negative_prompt`, `width`, `height`, `steps`, `seed`, `guidance`, `guidance_scale`, `style`!
- [x] **nano-banana-pro** - `docs/NANO_BANANA_PRO_INTEGRATION.md`
  - Обязательные: `prompt` (max 10000)
  - Опциональные: `image_input` (массив, до 8 изображений, max 30MB каждое, jpeg/png/webp), `aspect_ratio` (enum, 11 значений), `resolution` (enum: 1K/2K/4K), `output_format` (enum: png/jpg)
  - Default: `image_input=[]`, `aspect_ratio="1:1"`, `resolution="1K"`, `output_format="png"`
  - Важно: Может работать как t2i и i2i (если указан `image_input`)! Использует `aspect_ratio` вместо стандартных `width`/`height`! Использует `resolution` (1K/2K/4K) вместо стандартных значений! Уникальный параметр: `output_format` (png/jpg, не jpeg!)! `prompt` имеет максимум 10000 символов (больше чем у других моделей)! НЕТ параметров `negative_prompt`, `width`, `height`, `steps`, `seed`, `guidance`, `guidance_scale`, `style`!
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

