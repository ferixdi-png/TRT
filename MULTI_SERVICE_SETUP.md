# 🔧 НАСТРОЙКА НЕСКОЛЬКИХ RENDER СЕРВИСОВ

**Дата:** 2025-12-19

## 🎯 Назначение

Этот гайд поможет настроить несколько Render сервисов (Web Service и Worker) из одного GitHub проекта с разными токенами Telegram ботов.

## ✅ ЧТО СДЕЛАНО

1. ✅ `render.yaml` удалён из репозитория (чтобы не конфликтовал с разными сервисами)
2. ✅ Добавлен ENV-переключатель `ENABLE_HEALTH_SERVER` для управления health server
3. ✅ File lock защищает от двойного polling
4. ✅ Webhook удаляется перед polling

## 📋 НАСТРОЙКА КАЖДОГО СЕРВИСА В RENDER

### Web Service (требует открытый порт)

**Настройки в Render Dashboard:**

1. **Service Type:** Web Service
2. **Environment Variables:**
   ```
   ENABLE_HEALTH_SERVER=1
   TELEGRAM_BOT_TOKEN=ваш_токен_бота_1
   KIE_API_KEY=ваш_kie_api_key
   DATABASE_URL=YOUR_DATABASE_URL
   ADMIN_ID=ваш_telegram_id
   ```
3. **Start Command:** `python bot_kie.py`
4. **Build Command:** `pip install -r requirements.txt`

**Результат:**
- Health server запускается на порту `$PORT` (Render устанавливает автоматически)
- Health check: `https://your-service.onrender.com/health` → `ok`
- Нет ошибки "No open ports detected"

---

### Worker (не требует порт)

**Настройки в Render Dashboard:**

1. **Service Type:** Background Worker
2. **Environment Variables:**
   ```
   ENABLE_HEALTH_SERVER=0
   TELEGRAM_BOT_TOKEN=ваш_токен_бота_2
   KIE_API_KEY=ваш_kie_api_key
   DATABASE_URL=YOUR_DATABASE_URL
   ADMIN_ID=ваш_telegram_id
   ```
3. **Start Command:** `python bot_kie.py`
4. **Build Command:** `pip install -r requirements.txt`

**Результат:**
- Health server НЕ запускается
- Бот работает только в режиме polling
- Нет лишних HTTP запросов

---

## 🔐 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

### Обязательные (для всех сервисов):
- `TELEGRAM_BOT_TOKEN` - токен Telegram бота (разный для каждого сервиса!)
- `KIE_API_KEY` - API ключ KIE AI
- `DATABASE_URL` - строка подключения к PostgreSQL
- `ADMIN_ID` - ваш Telegram User ID

### Опциональные:
- `ENABLE_HEALTH_SERVER` - включить/выключить health server
  - `1` или не установлено = включено (для Web Service)
  - `0` = выключено (для Worker)
- `PORT` - порт для health server (Render устанавливает автоматически для Web Service)

---

## 📊 ПРОВЕРКА ПОСЛЕ ДЕПЛОЯ

### Web Service:
1. ✅ Логи: `✅ Health server listening on 0.0.0.0:XXXX`
2. ✅ Логи: НЕТ `No open ports detected`
3. ✅ URL: `https://your-service.onrender.com/health` → `ok`
4. ✅ Логи: `✅ Polling started successfully!`
5. ✅ Логи: НЕТ `409 Conflict`

### Worker:
1. ✅ Логи: `ℹ️ Health server disabled (ENABLE_HEALTH_SERVER=0) - running as Worker`
2. ✅ Логи: `✅ Polling started successfully!`
3. ✅ Логи: НЕТ `409 Conflict`

---

## 🚨 ЗАЩИТА ОТ КОНФЛИКТОВ

### File Lock
- Автоматически предотвращает двойной запуск бота
- Если другой экземпляр запущен - процесс завершается
- Логи: `✅ File lock acquired`

### Webhook Removal
- Webhook удаляется перед polling
- Проверка, что webhook действительно удалён
- Логи: `✅ Webhook удалён`

### Single Start Guard
- Polling запускается только один раз
- Защита от повторных запусков через `_POLLING_STARTED` флаг
- Логи: `✅ Polling started successfully!`

---

## 📝 ПРИМЕР НАСТРОЙКИ 2 СЕРВИСОВ

### Сервис 1: Основной бот (Web Service)
```
Service Name: kie-ai-bot-main
Service Type: Web Service
ENABLE_HEALTH_SERVER=1
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
```

### Сервис 2: Тестовый бот (Worker)
```
Service Name: kie-ai-bot-test
Service Type: Background Worker
ENABLE_HEALTH_SERVER=0
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
```

---

## ✅ ИТОГ

- ✅ `render.yaml` удалён - каждый сервис настраивается индивидуально
- ✅ `ENABLE_HEALTH_SERVER` управляет health server через ENV
- ✅ File lock защищает от двойного polling
- ✅ Webhook удаляется перед polling
- ✅ Работает с несколькими сервисами из одного GitHub проекта

**ВСЁ ГОТОВО! Настройте каждый сервис в Render Dashboard с нужными переменными окружения.**







