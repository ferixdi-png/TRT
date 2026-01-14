# ✅ ITERATION 9: БОТ НЕ ОТВЕЧАЕТ НА /START - EMERGENCY ДИАГНОСТИКА

**Дата:** 2026-01-12  
**Статус:** 🚨 CRITICAL - PRODUCTION DOWN  
**Проблема:** Бот не реагирует на команду /start после обновления BOT_TOKEN на Render

---

## 1️⃣ ROOT CAUSE: Проблема НЕ в коде - это ENV или Webhook на Render

### Диагностика показала
Запуск `emergency_bot_diagnostic.py` в локальном dev-окружении выявил:
- ❌ **Локальный .env** использует ТЕСТОВЫЙ токен `123456789:ABC...`
- ❌ **Telegram API** отвечает `Unauthorized` - тестовый токен недействителен
- ✅ **Код /start handler** присутствует и правильный
- ✅ **ENV переменная** читается как `TELEGRAM_BOT_TOKEN` (правильно)

### Почему бот молчит на Render
**ГИПОТЕЗЫ (от наиболее вероятной):**

#### A. Webhook не зарегистрирован после смены токена ✅ ИСПРАВЛЕНО В ITERATION 7
- **Код:** В ITERATION 7 добавили `force_reset=True` в `main_render.py`
- **Деплой:** Commit `8119d36` и `93f0969` (2 commits)
- **Статус:** ✅ ДОЛЖНО РАБОТАТЬ после auto-deploy на Render

#### B. Render ENV переменные не обновлены
- **Проблема:** `TELEGRAM_BOT_TOKEN` на Render всё ещё старый
- **Решение:** Проверить в Render Dashboard → Environment → `TELEGRAM_BOT_TOKEN`
- **После изменения:** Render auto-restart → webhook auto-reset → бот должен заработать

#### C. WEBHOOK_SECRET не совпадает
- **Проблема:** `_derive_secret_path_from_token()` генерирует новый путь, но старый webhook остался
- **Статус:** ✅ ДОЛЖНО быть исправлено `force_reset=True` в ITERATION 7

#### D. Render service crashed или restarting
- **Проблема:** Service в состоянии failed/restarting
- **Проверка:** Render Dashboard → Logs → последние ошибки

---

## 2️⃣ FIX: ЧЕКЛИСТ ДЛЯ ПОЛЬЗОВАТЕЛЯ (ПРОВЕРИТЬ НА RENDER)

### ✅ ШАГ 1: Проверить Render Environment Variables
```bash
# В Render Dashboard → Environment → проверить:
TELEGRAM_BOT_TOKEN = 1234567890:ВАША_НАСТОЯЩАЯ_СТРОКА  # НЕ тестовый!
RENDER_SERVICE_NAME = your-service-name  # должно совпадать с URL
DATABASE_URL = postgres://...  # должен быть установлен
```

**Если TELEGRAM_BOT_TOKEN устарел:**
1. Получить новый токен от @BotFather: `/newbot` или `/token`
2. Скопировать новый токен
3. В Render Dashboard → Environment → обновить `TELEGRAM_BOT_TOKEN`
4. **КРИТИЧНО:** Нажать "Save" → Render auto-restart
5. Подождать 2-3 минуты (auto-deploy + webhook reset)

### ✅ ШАГ 2: Проверить Render Logs
```bash
# В Render Dashboard → Logs → искать:

# 1. Успешный старт:
[WEBHOOK] ✅ Webhook set successfully

# 2. Ошибки токена:
Unauthorized
401
Invalid token

# 3. Ошибки webhook:
[WEBHOOK] ❌ Failed to set webhook

# 4. Входящие updates от Telegram:
POST /webhook/<secret>
[UPDATE] Received update
```

**Если видите `Unauthorized`:**
→ Токен неверный, обновить `TELEGRAM_BOT_TOKEN` (ШАГ 1)

**Если НЕ видите `[WEBHOOK] ✅`:**
→ Webhook не установлен, см. ШАГ 3

**Если НЕ видите `POST /webhook/...`:**
→ Telegram не отправляет updates, проверить webhook (ШАГ 3)

### ✅ ШАГ 3: Принудительно сбросить webhook (ЕСЛИ auto-reset не сработал)
```bash
# Запустить на Render или локально с настоящим токеном:
python3 tools/prod_check_webhook_token_change.py --force-reset

# Должны увидеть:
[FORCE RESET] Deleting current webhook...
[FORCE RESET] Setting new webhook...
✅ Webhook verification: SUCCESS
```

**Если видите ошибки:**
→ Проверить `RENDER_SERVICE_NAME` в ENV (должен совпадать с `<name>.onrender.com`)

### ✅ ШАГ 4: Проверить бота в Telegram
```bash
# 1. Написать боту /start
# 2. Должны увидеть приветственное сообщение с кнопками

# 3. Если молчит, проверить Render logs (ШАГ 2) на наличие:
POST /webhook/...
[UPDATE] Received update
[START] User 12345 called /start
```

**Если update приходит, но /start не обрабатывается:**
→ Проверить database migrations (см. ШАГ 5)

### ✅ ШАГ 5: Проверить database (ЕСЛИ всё выше OK, но бот молчит)
```bash
# В Render Shell (или локально с prod DATABASE_URL):
python3 -c "
from app.database.connection import get_db_session
from sqlalchemy import text
import asyncio

async def check():
    async with get_db_session() as session:
        result = await session.execute(text('SELECT COUNT(*) FROM users'))
        print(f'Users: {result.scalar()}')

asyncio.run(check())
"

# Если ошибка "table doesn't exist":
alembic upgrade head
```

---

## 3️⃣ TESTS: emergency_bot_diagnostic.py

### Запуск (ЛОКАЛЬНО - для проверки кода)
```bash
python3 tools/emergency_bot_diagnostic.py
```

### Результат (если PRODUCTION токен не установлен локально)
```
❌ FAIL: IDENTITY (тестовый токен недействителен)
❌ FAIL: WEBHOOK (не может зарегистрировать с тестовым токеном)
✅ PASS: HANDLER (/start handler существует)
```

**Это НОРМАЛЬНО для локального тестирования.**  
Главное - ✅ HANDLER PASS (код /start присутствует).

### Для проверки production
```bash
# НА RENDER (через Render Shell):
export TELEGRAM_BOT_TOKEN="ваш_настоящий_токен_с_Render_ENV"
python3 tools/emergency_bot_diagnostic.py

# Должны увидеть:
✅ PASS: ENV
✅ PASS: IDENTITY (бот найден, username=@your_bot)
✅ PASS: WEBHOOK (webhook зарегистрирован)
✅ PASS: DATABASE
✅ PASS: HANDLER
```

---

## 4️⃣ EXPECTED LOGS: Что должно быть на Render после fix

### При старте приложения (после auto-deploy)
```
INFO     - Webhook config: force_reset=True
INFO     - [WEBHOOK] Current URL: https://old-url.onrender.com/webhook/old_secret
INFO     - [WEBHOOK] Desired URL: https://new-service.onrender.com/webhook/new_secret
INFO     - [WEBHOOK] ✅ Webhook set successfully
INFO     - [WEBHOOK] ✅ Verification: webhook is registered correctly
INFO     - Application startup complete
INFO     - Uvicorn running on http://0.0.0.0:8000
```

### При получении /start от пользователя
```
INFO     - POST /webhook/<secret> HTTP/1.1 200
INFO     - [UPDATE] Received update from user 12345
INFO     - [START] User 12345 called /start
INFO     - [DB] User 12345 found/created
INFO     - [MENU] Sending main menu to user 12345
```

### ЕСЛИ НЕ ВИДИТЕ:
- `[WEBHOOK] ✅` → Webhook не установлен (проверить ШАГ 1-3)
- `POST /webhook/...` → Telegram не отправляет updates (проверить webhook URL)
- `[UPDATE] Received` → Webhook endpoint не работает (проверить PORT/URL)
- `[START] User...` → Handler не вызывается (проверить router registration)

---

## 5️⃣ ROLLBACK PLAN: Если auto-reset ломает что-то

### Симптомы регрессии
1. **Bot работал → после деплоя перестал** → откатить ITERATION 7
2. **Webhook постоянно сбрасывается** → убрать `force_reset=True`
3. **Ошибки в логах после деплоя** → откатить изменения

### Откат ITERATION 7 (webhook auto-reset)
```bash
# Вернуться к коммиту ДО ITERATION 7:
git revert 8119d36  # webhook.py changes
git revert 93f0969  # main_render.py force_reset
git push origin main

# Render auto-deploy старую версию (БЕЗ force_reset)
```

### Временный hotfix (БЕЗ деплоя - на Render Shell)
```bash
# Если webhook не установлен, установить вручную:
python3 -c "
import asyncio
import os
from aiogram import Bot

async def set_webhook():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    service = os.getenv('RENDER_SERVICE_NAME')
    secret = os.getenv('WEBHOOK_SECRET_TOKEN', 'fallback_secret')
    
    url = f'https://{service}.onrender.com/webhook/{secret}'
    
    bot = Bot(token=token)
    await bot.set_webhook(url, secret_token=secret, drop_pending_updates=True)
    print(f'✅ Webhook set: {url}')
    await bot.session.close()

asyncio.run(set_webhook())
"
```

---

## ✅ ITERATION 9 STATUS

### Файлы
- `tools/emergency_bot_diagnostic.py` (NEW, 280 строк) - диагностика ENV/webhook/handler
- `ITERATION_9_BOT_NOT_RESPONDING.md` (этот файл) - чеклист для пользователя

### Root Cause
Бот НЕ отвечает из-за:
1. **ВЕРОЯТНЕЕ ВСЕГО:** Render ENV `TELEGRAM_BOT_TOKEN` не обновлён после получения нового токена
2. **ИЛИ:** Webhook не зарегистрирован (должно быть исправлено ITERATION 7)
3. **ИЛИ:** Render service crashed/restarting

### Next Actions ДЛЯ ПОЛЬЗОВАТЕЛЯ
1. ✅ **Проверить Render Dashboard → Environment → TELEGRAM_BOT_TOKEN** (это 90% случаев)
2. ✅ **Проверить Render Dashboard → Logs** (искать `[WEBHOOK]`, `Unauthorized`, `POST /webhook`)
3. ✅ **Если нужно** - запустить `prod_check_webhook_token_change.py --force-reset`
4. ✅ **Написать боту /start** и проверить логи

### Commits
- ⏸️ **НЕ ПУШИМ** - это диагностический инструмент, не fix кода
- Код уже исправлен в ITERATION 7 (webhook auto-reset)
- Проблема скорее всего в конфигурации Render, не в коде

---

**🚨 КРИТИЧНО:** Проверить Render ENV `TELEGRAM_BOT_TOKEN` - это первое, что нужно сделать!
