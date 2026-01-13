# QUICK CHECK - Telegram Bot Health

Быстрая проверка бота на Render после деплоя (60 секунд).

## 🏥 1. HEALTH CHECK (общий статус)

```bash
curl -s https://five656.onrender.com/health | jq
```

**Ожидание**:
```json
{
  "status": "healthy",
  "bot_mode": "webhook",
  "lock_state": "ACTIVE",      // ✅ Должно быть ACTIVE
  "models_count": 1,            // z-image
  "queue": {
    "total_received": 456,
    "total_processed": 456,
    "total_dropped": 0,         // ❗ ДОЛЖНО БЫТЬ 0
    "total_held": 23,
    "total_requeued": 23,       // >0 если были PASSIVE периоды
    "total_processed_degraded": 0
  }
}
```

**Проблемы**:
- ❌ `lock_state: "PASSIVE"` дольше 5s → проверь PostgreSQL locks
- ❌ `total_dropped > 0` → **КРИТИЧНО** - requeue не работает
- ⚠️ `total_processed_degraded > 10` → долгий PASSIVE

## 🌐 2. WEBHOOK STATUS

```bash
curl -s https://five656.onrender.com/diag/webhook | jq
```

**Ожидание**:
```json
{
  "pending_update_count": 0,   // ❗ ДОЛЖНО БЫТЬ 0-2
  "last_error_message": "",    // ❗ ДОЛЖНО БЫТЬ ПУСТО
  "url": "https://five656.onrender.com/webhook"
}
```

**Проблемы**:
- ❌ `pending_update_count > 10` → Automatic flush сработает
- ❌ `last_error_message != ""` → смотри типы:
  - `"Read timeout expired"` → Workers медленные (FIXED via fast-ack)
  - `"Connection reset"` → Render перезапускает
  - `"Wrong response"` → Crash в webhook handler

## 🤖 3. TELEGRAM /start TEST

**Команда**: Отправь `/start` в [@five656robot](https://t.me/five656robot)

**Ожидание**:
1. ⏱ <1s: "✅ Бот на связи..."
2. ⏱ <2s: Полное меню с кнопками

**Проблемы**:
- ❌ Молчит >5s → проверь `/health` lock_state и `/diag/webhook` pending
- ❌ "Ошибка" → смотри Render logs `[START]` и `ERROR`

## ✅ QUICK CHECKLIST (выполни за 60 секунд)

```bash
#!/bin/bash
echo "1. Health status..."
curl -s https://five656.onrender.com/health | jq -r '.status, .lock_state'

echo "2. Webhook pending..."
curl -s https://five656.onrender.com/diag/webhook | jq '.pending_update_count'

echo "3. Queue drops..."
curl -s https://five656.onrender.com/health | jq '.queue.total_dropped'

echo "4. Last error..."
curl -s https://five656.onrender.com/diag/webhook | jq -r '.last_error_message'

echo "✅ OK если: status=healthy, lock_state=ACTIVE, pending=0, drops=0, error=''"
```

## 🎯 SUCCESS CRITERIA

Бот **ЗДОРОВ**, если:

- [x] `/health` → `status: "healthy"`
- [x] `/health` → `lock_state: "ACTIVE"`
- [x] `/health` → `queue.total_dropped == 0`
- [x] `/diag/webhook` → `pending_update_count < 3`
- [x] `/diag/webhook` → `last_error_message == ""`
- [x] Telegram /start → ответ <1s

## 🔴 Красные флаги

Если видите это → проблема:
- ❌ `pending_update_count > 10` в /diag/webhook
- ❌ `last_error_message != ""` в /diag/webhook
- ❌ /start не отвечает >3 секунд
- ❌ В логах: `[WEBHOOK] Read timeout expired`

## 🧪 SINGLE_MODEL Test (опционально)

Если включили `SINGLE_MODEL_ONLY=1`:

1. /start → кнопка "🖼 Создать картинку"
2. Нажать → "Опишите картинку"
3. Ввести: "кот в космосе"
4. Выбрать формат: "1:1"
5. Подождать 10-30 сек
6. ✅ Получить фото

## 📊 Мониторинг (каждый час первые сутки)

```bash
# Webhook health
curl $APP_URL/diag/webhook | jq .pending_update_count

# Queue health
curl $APP_URL/health | jq .queue.drop_rate

# Оба должны быть близки к 0
```

## 🆘 Если что-то сломалось

1. **Откат коммита**:
```bash
git revert HEAD
git push origin main
```

2. **Или откат через Render UI**:
   - Settings → Deploys
   - Найти предыдущий успешный deploy
   - Нажать "Deploy"

3. **Диагностика**:
   - Проверить логи Render: Build Logs + Deploy Logs
   - Проверить ENV variables (все обязательные присутствуют?)
   - Проверить `/health` (503 = не стартовал)

## ✅ Критерии успеха

- [x] /start отвечает <1s
- [x] pending_update_count = 0
- [x] last_error_message пустой
- [x] В логах: WEBHOOK CONFIGURED
- [x] В логах: Workers started
- [x] (опционально) Z-image работает end-to-end

---

**Быстрая проверка = 2 минуты**  
**Полная проверка = 5 минут**  
**SINGLE_MODEL тест = 1 минута**

Если все ✅ → деплой успешен! 🎉
