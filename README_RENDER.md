# 🚀 KIE Telegram Bot - Версия для Render.com

## 📁 Эта папка содержит все файлы для развертывания на Render.com

### ✅ Что включено:

- ✅ Все Python файлы бота
- ✅ Dockerfile для Render
- ✅ Node.js wrapper (index.js)
- ✅ Все конфигурационные файлы
- ✅ Инструкции по развертыванию

### 🚀 Быстрый старт:

1. **Загрузите все файлы в GitHub репозиторий**

2. **Откройте Render.com:**
   - https://dashboard.render.com/
   - Создайте Web Service
   - Подключите GitHub репозиторий

3. **Настройки:**
   - Environment: **Docker**
   - Branch: **main**

4. **Переменные окружения:**
   ```
   TELEGRAM_BOT_TOKEN=ваш_новый_токен (ПОСЛЕ /revoke в BotFather!)
   KIE_API_KEY=ваш_ключ
   ADMIN_ID=ваш_id
   
   # CRITICAL: Для масштабирования (multi-instance safe locks) ⚠️
   # Обязательно при запуске 2+ инстансов:
   DATABASE_URL=postgresql://user:***REDACTED***@host:5432/dbname
   REDIS_URL=redis://host:6379/0
   
   # Без DATABASE_URL/REDIS_URL:
   #   lock_mode=file, lock_degraded=true (НЕ безопасно для 2+ инстансов!)
   # С DATABASE_URL:
   #   lock_mode=postgres, lock_degraded=false ✅ (safe для 2+ инстансов)
   # С REDIS_URL:
   #   Дополнительное хранилище: сессии, кэш, дедупликация callback'ов
   ```
   **ВАЖНО:** Токен уже скомпрометирован — используйте /revoke в BotFather и установите новый!

5. **Запустите!**

### 📄 Инструкции:

- **RENDER_QUICK_START.md** - быстрый старт (5 минут)
- **RENDER_DEPLOY.md** - подробная инструкция

### 📦 Структура:

```
render/
├── Dockerfile              # Docker конфигурация
├── index.js                # Node.js wrapper
├── package.json            # Node.js зависимости
├── entrypoints/run_bot.py  # Канонический Python entrypoint
├── run_bot.py              # Wrapper (совместимость)
├── bot_kie.py              # Основная логика бота
├── requirements.txt        # Python зависимости
├── render.yaml             # Конфигурация Render (опционально)
└── ...                     # Все остальные файлы
```

### ▶️ Render entrypoint + ключевые ENV (канонично)

- **Entrypoint (SSOT):** `python entrypoints/run_bot.py`
- **Webhook-режим (Web Service):**
  - `BOT_MODE=webhook`
  - `TELEGRAM_BOT_TOKEN=...`
  - `WEBHOOK_URL=https://<service>.onrender.com/webhook`
  - `PORT=10000` (healthcheck server)
  - `AUTO_SET_WEBHOOK=1` (авто-установка webhook при старте)
  - `REQUIRE_WEBHOOK_REGISTERED=1` (fail-fast если webhook не зарегистрирован)
- **Хранилище:**
  - `STORAGE_MODE=db` + `DATABASE_URL=...` (Postgres)
  - `REDIS_URL=...` (опционально, быстрые distributed locks)
- **Опционально:** `KIE_API_KEY=...`, `BOT_INSTANCE_ID=partner-01`, `ENABLE_HEALTH_SERVER=1`

### 🔁 Поведение webhook при сбое Telegram API

- Если `setWebhook` не отвечает/таймаутит, сервис **не завершает процесс**.
- Установка webhook уходит в фоновый retry-контур с backoff (короткие таймауты, 2–3 попытки на цикл).
- Когда Telegram снова доступен, webhook подтверждается автоматически.

### ⚠️ Важно:

- Файл `.env` НЕ должен быть в репозитории
- Используйте переменные окружения в панели Render
- На бесплатном плане сервис "засыпает" после 15 минут

---

**Готово к развертыванию! 🎉**
