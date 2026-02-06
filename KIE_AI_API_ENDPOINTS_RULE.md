# 🔴 ОБЯЗАТЕЛЬНОЕ ПРАВИЛО: API ENDPOINTS

## ГЛАВНОЕ ПРАВИЛО ДЛЯ ВСЕХ МОДЕЛЕЙ KIE AI

**ВСЕ модели ДОЛЖНЫ использовать API Endpoints строго по официальной документации:**

### 📚 ИСТОЧНИКИ:

1. **https://docs.kie.ai/** - Comprehensive API Documentation (официальная документация)
   - Полная документация всех API Endpoints
   - Quickstart guides для каждой модели
   - API Reference с полными параметрами
   - Code Samples и примеры

2. **https://docs.kie.ai/market** - Market Documentation (ОБЯЗАТЕЛЬНО!)
   - **Image Models** - все модели генерации изображений
   - **Video Models** - все модели генерации видео
   - **Audio Models** - все модели обработки аудио
   - Документация для каждой модели в Market
   - Unified API Structure для всех моделей

3. **https://kie.ai/ru** - Русская версия сайта
   - Информация о моделях и ценах
   - API Endpoints документация

4. **https://docs.kie.ai/file-upload-api** - File Upload API (ОБЯЗАТЕЛЬНО для загрузки файлов!)
   - URL File Upload - для загрузки файлов с удаленных URL
   - File Stream Upload - для загрузки локальных файлов (рекомендуется для больших файлов)
   - Base64 Upload - для загрузки файлов в формате Base64 (для маленьких файлов)
   - Все файлы автоматически удаляются через 3 дня

5. **https://docs.kie.ai/llms.txt** - Навигация по документации

**НИКАКИХ отклонений от официальной документации API Endpoints!**

---

## ✅ ЧТО ЭТО ОЗНАЧАЕТ:

1. **Все параметры** должны соответствовать документации на https://docs.kie.ai/
2. **Все форматы** параметров должны быть строго по документации
3. **Все конвертации** параметров должны быть согласно документации
4. **Все валидации** должны проверять соответствие документации
5. **Никаких дополнительных параметров**, которых нет в документации
6. **Никаких изменений формата** без проверки документации
7. **Все API Endpoints** должны использоваться строго по официальной документации

---

## 📋 ПРИМЕРЫ ПРАВИЛЬНОГО ИСПОЛЬЗОВАНИЯ:

### ✅ ПРАВИЛЬНО:
- Использовать `image_url` (string) для `kling/v2-1-pro` согласно документации
- Использовать `video_url` и `image_url` (strings) для `wan/2-2-animate-replace` согласно документации
- Использовать `aspect_ratio: "auto"` для `wan/2-2-a14b-image-to-video-turbo` согласно документации

### ❌ НЕПРАВИЛЬНО:
- Использовать `image_input` (array) для `kling/v2-1-pro` (должно быть `image_url` string)
- Использовать `video_input` и `image_input` (arrays) для `wan/2-2-animate-replace` (должны быть `video_url` и `image_url` strings)
- Добавлять параметр `prompt` для `wan/2-2-animate-replace` (его нет в документации)

---

## 🔍 КАК ПРОВЕРИТЬ:

1. Откройте https://docs.kie.ai/market - Market Documentation
2. Найдите нужную модель в соответствующей категории:
   - **Image Models** - для моделей генерации изображений
   - **Video Models** - для моделей генерации видео
   - **Audio Models** - для моделей обработки аудио
3. Откройте страницу конкретной модели в Market
4. Проверьте Quickstart guide для модели
5. Проверьте API Reference с полными параметрами
6. Убедитесь, что все параметры соответствуют документации
7. Убедитесь, что все форматы соответствуют документации
8. Используйте Code Samples как эталон для правильного формата
9. Проверьте Unified API Structure (POST /api/v1/jobs/createTask, GET /api/v1/jobs/recordInfo)
10. Проверьте llms.txt (https://docs.kie.ai/llms.txt) для навигации

---

## ⚠️ ВАЖНО:

**Это правило применяется ко ВСЕМ моделям без исключений!**

**Любые изменения должны быть проверены против официальной документации:**
- **https://docs.kie.ai/** - Comprehensive API Documentation
- **https://docs.kie.ai/market** - Market Documentation (ОБЯЗАТЕЛЬНО для всех моделей!)
- **https://docs.kie.ai/file-upload-api** - File Upload API (ОБЯЗАТЕЛЬНО для загрузки файлов!)
- **https://kie.ai/ru** - Русская версия сайта

**Используйте Interactive Examples и Code Samples из документации как эталон!**

**ВАЖНО: Все модели находятся в Market Documentation - используйте его как основной источник!**

**ВАЖНО: Для загрузки файлов (изображений, видео, аудио) ОБЯЗАТЕЛЬНО использовать KIE AI File Upload API, а не внешние хостинги!**

---

---

## 📖 О ДОКУМЕНТАЦИИ KIE.AI

Kie.ai предоставляет:
- **99.9% Uptime** - Надежная и стабильная производительность API
- **Affordable Pricing** - Гибкая система ценообразования на основе кредитов
- **High Concurrency** - Масштабируемые решения
- **24/7 Support** - Профессиональная техническая поддержка
- **Secure Integration** - Безопасность данных корпоративного уровня

### Документация включает:
- **Interactive Examples** - Тестирование API прямо в документации
- **Code Samples** - Готовые примеры на нескольких языках программирования
- **Comprehensive Guides** - Пошаговые инструкции по интеграции
- **API Reference** - Полная документация параметров и схем ответов
- **Best Practices** - Советы по оптимизации и распространенные случаи использования

---

---

## 📖 О MARKET DOCUMENTATION

Market Documentation (https://docs.kie.ai/market) содержит:

### Image Models:
- Seedream (v4.0, v4.5)
- Grok Imagine
- Flux-2 (pro-text-to-image, pro-image-to-image, flex-text-to-image, flex-image-to-image)
- Google Imagen (Imagen4, Imagen4 Fast, Imagen4 Ultra)
- Ideogram (v3-text-to-image, v3-edit, v3-reframe)
- Qwen (text-to-image, image-to-image, image-edit)
- Recraft (crisp-upscale, remove-background)
- Topaz (image-upscale)

### Video Models:
- Kling (v2-1-pro, v2-1-standard, v2-5-turbo, v1-avatar)
- Sora2 (sora-2-text-to-video, sora-2-pro-image-to-video, sora-2-pro-storyboard)
- Bytedance (v1-pro-text-to-video, v1-pro-image-to-video, v1-lite-image-to-video)
- Hailuo (2-3-image-to-video-pro, 2-3-image-to-video-standard, 02-text-to-video-pro, 02-image-to-video-pro, 02-text-to-video-standard, 02-image-to-video-standard)
- Wan (2-2-a14b-text-to-video-turbo, 2-2-a14b-image-to-video-turbo, 2-2-a14b-speech-to-video-turbo, 2-2-animate-move, 2-2-animate-replace, 2-5-text-to-video, 2-5-image-to-video)
- Grok Imagine Video

### Audio Models:
- ElevenLabs (text-to-speech, speech-to-text, audio-isolation, sound-effect)
- Infinitalk (from-audio)

### Unified API Structure:
- **POST** https://api.kie.ai/api/v1/jobs/createTask - Create Task
- **GET** https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId} - Query Task Status
- **Callback Notifications** - Optional webhook callbacks

---

## 📤 FILE UPLOAD API (ОБЯЗАТЕЛЬНО!)

**ВСЕ файлы (изображения, видео, аудио) ДОЛЖНЫ загружаться через KIE AI File Upload API!**

### Base URL:
```
https://kieai.redpandaai.co
```

### Authentication:
```http
Authorization: Bearer YOUR_KIE_API_KEY
```

### Endpoints:

1. **URL File Upload** - для загрузки файлов с удаленных URL
   - **POST** https://kieai.redpandaai.co/api/file-url-upload
   - Параметры: `fileUrl` (required), `uploadPath` (optional), `fileName` (optional)
   - Подходит для: миграции файлов, пакетной обработки
   - Ограничения: публично доступный URL, таймаут 30 секунд, рекомендуется ≤100MB

2. **File Stream Upload** - для загрузки локальных файлов
   - **POST** https://kieai.redpandaai.co/api/file-stream-upload
   - Параметры: `file` (required, multipart/form-data), `uploadPath` (optional), `fileName` (optional)
   - Подходит для: больших файлов, локальных файлов
   - Преимущества: высокая эффективность передачи, поддержка больших файлов

3. **Base64 Upload** - для загрузки файлов в формате Base64
   - **POST** https://kieai.redpandaai.co/api/file-base64-upload
   - Параметры: `base64Data` (required), `uploadPath` (optional), `fileName` (optional)
   - Подходит для: маленьких файлов (≤10MB), интеграции через JSON
   - Ограничения: размер данных увеличивается на 33%, не подходит для больших файлов

### Важные правила:

- ✅ **ОБЯЗАТЕЛЬНО использовать KIE AI File Upload API** для всех загрузок файлов
- ✅ **НЕ использовать внешние хостинги** (0x0.st, catbox.moe, transfer.sh и т.д.)
- ⚠️ **Файлы автоматически удаляются через 3 дня** - важно скачать или мигрировать важные файлы
- ✅ Использовать `fileUrl` из ответа API для передачи в модели KIE AI
- ✅ Параметр `fileName` опционален - если не указан, генерируется случайное имя
- ✅ При повторной загрузке с тем же `fileName` старый файл перезаписывается (с учетом кэширования)

### Response Format:
```json
{
  "success": true,
  "code": 200,
  "msg": "File uploaded successfully",
  "data": {
    "fileId": "file_abc123456",
    "fileName": "my-image.jpg",
    "originalName": "sample-image.jpg",
    "fileSize": 245760,
    "mimeType": "image/jpeg",
    "uploadPath": "images",
    "fileUrl": "https://kieai.redpandaai.co/files/images/my-image.jpg",
    "downloadUrl": "https://kieai.redpandaai.co/download/file_abc123456",
    "uploadTime": "2025-01-15T10:30:00Z",
    "expiresAt": "2025-01-18T10:30:00Z"
  }
}
```

### Выбор метода загрузки:

- **Маленькие файлы (≤1MB)**: Base64 Upload
- **Средние файлы (1MB-10MB)**: File Stream Upload
- **Большие файлы (>10MB)**: File Stream Upload (обязательно)
- **Удаленные файлы**: URL File Upload (рекомендуется ≤100MB)

**Документация:** https://docs.kie.ai/file-upload-api

---

**Дата фиксации правила:** 2025-12-16  
**Статус:** ✅ ОБЯЗАТЕЛЬНО ДЛЯ ВСЕХ МОДЕЛЕЙ  
**Источники:** 
- https://docs.kie.ai/market (Market Documentation - ОБЯЗАТЕЛЬНО!)
- https://docs.kie.ai/file-upload-api (File Upload API - ОБЯЗАТЕЛЬНО для загрузки файлов!)
- https://docs.kie.ai/ (Comprehensive API Documentation)
- https://kie.ai/ru (Русская версия)


