# TRT Production Report (2026-01-12)

## 🎯 Цель: Стабильный Production на Render (webhook mode)

Задача: довести бот до стабильного production на Render через существующие ENV из Secrets, без хардкода и новых ключей.

---

## ✅ Что изменено

### 1. **Minimal Happy Path для z-image** (`minimal_happy_path.py`)

**Что делает:**
- Валидирует обязательные ENV переменные (TELEGRAM_BOT_TOKEN, DATABASE_URL, WEBHOOK_BASE_URL, KIE_API_KEY, PORT, BOT_MODE)
- Проверяет lock key в signed int64 range [0, 2^63-1]
- Проверяет миграции БД (idempotent)
- Настраивает webhook на WEBHOOK_BASE_URL
- Тестирует полный цикл z-image: создание задачи → проверка статуса

**Зачем:**
- Автономная проверка production-readiness
- Валидация всех критических компонентов
- Гарантия корректной настройки webhook

**Файлы:**
- `minimal_happy_path.py` - основной скрипт валидации

---

### 2. **Idempotent Migrations** (`init_schema_idempotent.sql`)

**Что делает:**
- Создает только необходимые таблицы: `users`, `generation_jobs`, `orphan_callbacks`
- Безопасно для повторного выполнения (IF NOT EXISTS, IF EXISTS)
- Добавляет helper-функцию `ensure_user()` для upsert
- Создает триггеры для auto-update `updated_at`

**Зачем:**
- Убирает падения из-за "consolidate_schema" и других ломающихся миграций
- Гарантирует идемпотентность (можно применять многократно)
- Минимальная схема для happy path (z-image)

**Файлы:**
- `init_schema_idempotent.sql` - SQL schema для production

---

### 3. **Фикс дублирования init_active_services** (`main_render.py`)

**Проблема:**
- `state_sync_loop()` вызывал `init_active_services()` повторно при переходе PASSIVE→ACTIVE
- Это дублировало вызов callback из `lock_controller`
- Webhook мог настраиваться дважды

**Решение:**
- Убран вызов `await init_active_services()` из `state_sync_loop()`
- Callback вызывается только из `SingletonLockController._set_state()`
- Добавлен лог: "Services already initialized by controller callback"

**Файлы:**
- `main_render.py` (строки 957-970)

---

### 4. **Production Smoke Test** (`prod_check.py`)

**Что делает:**
Полная e2e валидация production-readiness:
1. ENV переменные (все обязательные)
2. Порт открыт (PORT)
3. Миграции БД (применяет `init_schema_idempotent.sql`)
4. Lock key (int64 signed range)
5. Webhook настроен на WEBHOOK_BASE_URL
6. Health endpoint (/health) - опционально
7. Полный цикл z-image (create task → check status)

**Exit codes:**
- 0: ✅ Все проверки прошли
- 1: ❌ Критическая ошибка

**Файлы:**
- `prod_check.py` - e2e smoke test

---

## 🔧 Как проверить локально (Codespaces)

### Вариант 1: Minimal Happy Path (рекомендуется)

```bash
# 1. Установить зависимости (если еще не установлены)
pip install -r requirements.txt

# 2. Убедиться, что ENV переменные установлены
# В Codespaces используйте Secrets или .env файл

# 3. Запустить валидацию
python3 minimal_happy_path.py
```

**Ожидаемый результат:**
```
✅ All required ENV variables present
✅ Lock key valid: 1234567890123456789
✅ Required tables present: users, generation_jobs, orphan_callbacks
✅ Webhook set: https://your-app.onrender.com/8524869517AAH...
✅ Task created: task_12345
✅ Task status: pending
```

---

### Вариант 2: Full Production Smoke Test

```bash
python3 prod_check.py
```

**Ожидаемый результат:**
```
✅ ✅ ✅ ALL CRITICAL TESTS PASSED ✅ ✅ ✅
Summary:
  1. ENV variables: ✅
  2. Port 10000: ✅
  3. Migrations: ✅
  4. Lock key: ✅
  5. Webhook: ✅
  6. Health endpoint: ✅
  7. Z-image flow: ✅
Production Ready! 🚀
```

---

### Вариант 3: Запустить основной бот

```bash
python3 main_render.py
```

**Что проверить в логах:**
1. `[LOCK] ✅ ACTIVE MODE: PostgreSQL advisory lock acquired`
2. `[WEBHOOK_SETUP] ✅ ✅ ✅ WEBHOOK CONFIGURED SUCCESSFULLY`
3. `[HEALTH] ✅ Server started on port 10000`
4. Нет ошибок "OID out of range"
5. Нет спама "updating" или "no open ports detected"

---

## 📊 Как проверить на Render (по логам)

### Чеклист для Render Logs

#### 1. **Старт контейнера**
```
[OK] Data directory writable: /tmp/data
[BUILD] Application created successfully
```

#### 2. **Миграции (idempotent)**
Если используете `init_schema_idempotent.sql` через psql:
```
CREATE TABLE
CREATE INDEX
CREATE FUNCTION
CREATE TRIGGER
```

Если используете main_render.py:
```
[DB] ✅ DatabaseService initialized
```

#### 3. **Lock acquisition**
**АКТИВНЫЙ режим (норма):**
```
[LOCK] ✅ ACTIVE MODE: PostgreSQL advisory lock acquired
```

**PASSIVE режим (deploy overlap - норма):**
```
[LOCK] ⏸️ PASSIVE MODE: Webhook will return 200 but no processing
[LOCK] Background retry task started
```

**PASSIVE→ACTIVE переход (норма через 10-60s):**
```
[LOCK] ✅ PASSIVE → ACTIVE: Lock acquired on retry 4!
[LOCK_CONTROLLER] 🔥 Calling on_active_callback...
[WEBHOOK_SETUP] ✅ ✅ ✅ WEBHOOK CONFIGURED SUCCESSFULLY
```

#### 4. **Webhook настройка**
```
[WEBHOOK_SETUP] 🔧 Calling ensure_webhook (force_reset=True)...
[WEBHOOK_SETUP] ✅ ✅ ✅ WEBHOOK CONFIGURED SUCCESSFULLY
[WEBHOOK_SETUP] ✅ Bot will now receive /start and other commands
```

#### 5. **HTTP сервер**
```
[HEALTH] ✅ Server started on port 10000
```

#### 6. **Health checks**
```
127.0.0.1 - - "GET /health HTTP/1.1" 200
```

---

### ❌ Проблемные логи (что НЕ должно быть)

#### Плохо 1: OID out of range
```
psycopg2.errors.NumericValueOutOfRange: OID out of range
```
**Решение:** Уже исправлено в `render_singleton_lock.py` (commit 3ca2fec) - используется bitwise mask `& 0x7FFFFFFFFFFFFFFF`

#### Плохо 2: Webhook не настроен
```
[WEBHOOK_SETUP] ❌ Failed to set webhook! Bot will NOT receive updates.
```
**Решение:** Проверить WEBHOOK_BASE_URL в Render Secrets, убедиться что callback вызывается

#### Плохо 3: Миграции падают
```
psycopg2.errors.DuplicateTable: relation "users" already exists
```
**Решение:** Использовать `init_schema_idempotent.sql` (IF NOT EXISTS)

#### Плохо 4: Нет lock, FORCE ACTIVE
```
[LOCK] ⚠️ FORCE ACTIVE MODE (risky!)
```
**Решение:** Нормально только при LOCK_MODE=wait_then_force (не рекомендуется для production)

---

## 🚀 Деплой на Render

### Шаг 1: Убедиться что ENV установлены

В Render Dashboard → Environment:
- ✅ `TELEGRAM_BOT_TOKEN` - токен бота
- ✅ `DATABASE_URL` - PostgreSQL URL
- ✅ `WEBHOOK_BASE_URL` - https://your-app.onrender.com
- ✅ `KIE_API_KEY` - kie.ai API ключ
- ✅ `PORT` - 10000 (автоматически)
- ✅ `BOT_MODE` - webhook
- ✅ `ADMIN_ID`, `PAYMENT_*`, `SUPPORT_*` - опциональные

### Шаг 2: Deploy

**Автодеплой (рекомендуется):**
```bash
git add .
git commit -m "fix: production stability (idempotent migrations + webhook callback)"
git push origin main
```

Render автоматически:
1. Запустит build
2. Применит миграции (если настроены)
3. Запустит main_render.py
4. Старый инстанс получит SIGTERM и освободит lock
5. Новый инстанс захватит lock и настроит webhook

### Шаг 3: Проверить логи

```bash
# В Render Dashboard → Logs
# Искать:
[LOCK] ✅ ACTIVE MODE
[WEBHOOK_SETUP] ✅ ✅ ✅ WEBHOOK CONFIGURED
[HEALTH] ✅ Server started on port 10000
```

### Шаг 4: Протестировать бот

1. Отправить `/start` в Telegram
2. Убедиться что бот отвечает (главное меню)
3. Выбрать z-image
4. Ввести prompt + aspect_ratio
5. Дождаться результата (image URL)

---

## 📝 Технические детали

### Lock Key (int64 signed)

**Проблема:** `unsigned_key % (MAX_BIGINT + 1)` давал [0, 2^63], что выходило за signed int64
**Решение:** Bitwise mask `unsigned_key & 0x7FFFFFFFFFFFFFFF` гарантирует [0, 2^63-1]

**Код:**
```python
# render_singleton_lock.py, lines 27-56
MAX_BIGINT = 0x7FFFFFFFFFFFFFFF  # 2^63 - 1
lock_key = unsigned_key & MAX_BIGINT
```

---

### Idempotent Migrations

**Принцип:** Все DDL команды используют IF EXISTS / IF NOT EXISTS

**Примеры:**
```sql
CREATE TABLE IF NOT EXISTS users (...);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at ...;
```

**Безопасность:** Можно применять многократно без ошибок

---

### Webhook Callback

**Архитектура:**
1. `SingletonLockController` создается с `on_active_callback=init_active_services`
2. При захвате lock: `_set_state(ACTIVE)` → вызывает callback
3. Callback: `init_active_services()` → `ensure_webhook()`
4. Webhook настраивается ровно 1 раз при переходе PASSIVE→ACTIVE

**Проблема (исправлена):**
- `state_sync_loop()` дублировал вызов `init_active_services()`
- Теперь только логирует: "Services already initialized by controller callback"

---

## 🔍 Диагностика проблем

### Бот не отвечает на /start

**Проверить:**
1. `[WEBHOOK_SETUP] ✅ WEBHOOK CONFIGURED` в логах Render
2. `await bot.get_webhook_info()` - должен вернуть URL
3. WEBHOOK_BASE_URL правильный (https://, без trailing slash)
4. Нет ошибок "Failed to set webhook"

**Фикс:**
```bash
python3 minimal_happy_path.py  # Настроит webhook автоматически
```

---

### Lock не захватывается (вечный PASSIVE)

**Проверить:**
1. Нет ли зависших процессов на Render (старый deploy не завершился)
2. `DATABASE_URL` корректный
3. Stale lock detection работает (idle >300s → terminate)

**Фикс:**
```sql
-- Force release lock (крайний случай)
SELECT pg_advisory_unlock_all();
```

---

### Миграции падают

**Проверить:**
1. Используется ли `init_schema_idempotent.sql`
2. Нет ли conflicting миграций в `alembic/versions/`

**Фикс:**
```bash
# Применить idempotent schema вручную
psql $DATABASE_URL < init_schema_idempotent.sql
```

---

## 📦 Файлы в репозитории

### Новые файлы (созданы в этом сеансе):
- `minimal_happy_path.py` - валидация production-readiness
- `init_schema_idempotent.sql` - idempotent миграции
- `prod_check.py` - e2e smoke test
- `TRT_REPORT.md` - этот файл

### Измененные файлы:
- `main_render.py` - фикс дублирования callback (строки 957-970)

### Существующие файлы (без изменений):
- `render_singleton_lock.py` - lock key уже исправлен (commit 3ca2fec)
- `app/locking/controller.py` - callback механизм уже рабочий
- `models/kie_models.yaml` - z-image конфигурация

---

## ✅ Итого

### Что работает:
1. ✅ Идемпотентные миграции (safe для повторного применения)
2. ✅ Lock key в signed int64 range (no OID errors)
3. ✅ Webhook настраивается ровно 1 раз при PASSIVE→ACTIVE
4. ✅ Stale lock detection (kill idle >5min)
5. ✅ Minimal happy path для z-image (валидация всего стека)
6. ✅ E2E smoke test (7 проверок production-readiness)

### Что осталось:
- ⚠️ Deploy на Render и проверка логов (ждем user action)
- ⚠️ Тест /start в Telegram после деплоя

### Рекомендации для production:
1. Использовать `init_schema_idempotent.sql` вместо alembic (если миграции ломаются)
2. Мониторить логи на наличие `[WEBHOOK_SETUP] ✅ WEBHOOK CONFIGURED`
3. При редеплое: нормально видеть PASSIVE→ACTIVE переход (10-60s)
4. Если бот не отвечает: запустить `python3 minimal_happy_path.py`

---

**Отчет создан:** 2026-01-12  
**Commit с изменениями:** Следующий коммит после этого отчета  
**Статус:** ✅ Ready for Render deployment
