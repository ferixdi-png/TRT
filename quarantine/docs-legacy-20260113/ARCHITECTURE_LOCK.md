# ARCHITECTURE_LOCK.md
**Единая архитектурная истина проекта TRT**

## Цель продукта
Telegram-бот для генерации изображений через API КИЕ с балансовой системой, подпиской и административными функциями.

## Definition of Done (DOD)

### Критерии готовности к релизу
1. ✅ **Health endpoint**: `/health` возвращает 200 OK с валидным JSON (все поля сериализуемы)
2. ✅ **Singleton lock**: PostgreSQL advisory lock работает без OID overflow/type errors
3. ✅ **PASSIVE UX**: Callback queries получают instant ack в PASSIVE режиме (нет "вечной крутилки")
4. ✅ **Логи чистые**: 0 ERROR/Traceback в Render логах за 10 минут после деплоя
5. ✅ **Smoke scenarios**: S0 (health), S1 (bot responsive), S2 (storage) — все PASS
6. ⏳ **CI gates**: verify_truth.py + smoke_test.py проходят в CI
7. ⏳ **Entrypoint контракт**: Один и только один production entrypoint
8. ⏳ **Queue stability**: Очередь webhook updates не растёт бесконечно
9. ⏳ **Repo hygiene**: Дубликаты/legacy код изолированы в quarantine/
10. ⏳ **Regression safety**: Каждый деплой проходит automated gates

## Архитектура

### Entrypoint (Production)
**Единственный точка входа**: `main_render.py`

```
Render Web Service → main_render.py → aiohttp app
├── /webhook → UpdateQueueManager → aiogram Dispatcher
├── /health → runtime_state + lock_debug + queue_metrics
├── /kie-callback → KIE payment webhook
└── / → redirect to /health
```

### Поток данных (Webhook Flow)
```
1. Telegram → POST /webhook → enqueue() → 200 OK (fast-ack)
2. Background workers → asyncio.Queue → Dispatcher.feed_update()
3. Handlers (app/handlers/) → DatabaseService → response
4. Callback queries → answer_callback_query() (immediate, always)
```

### Роли инстансов
- **ACTIVE**: Держит PostgreSQL advisory lock, обрабатывает все updates, webhook установлен
- **PASSIVE**: Не держит lock, обрабатывает только whitelist (/start, menu:*), instant reject остальных

### Компоненты (Immutable Core)
- **Locking**: `app/locking/controller.py` + `render_singleton_lock.py` (PostgreSQL advisory lock с heartbeat)
- **Queue**: `app/utils/update_queue.py` (asyncio.Queue с метриками и PASSIVE logic)
- **Storage**: `app/database/services.py` (DatabaseService с транзакциями)
- **Handlers**: `app/handlers/` (aiogram handlers, декларативный routing)
- **Webhook**: `app/utils/webhook.py` (set/delete webhook, KIE callbacks)

## Контракты

### Environment Variables (Required)
```bash
# КРИТИЧНЫЕ (без них не стартует)
TELEGRAM_BOT_TOKEN       # Токен Telegram бота
DATABASE_URL             # PostgreSQL connection string (для lock + storage)
RENDER_EXTERNAL_URL      # Base URL для webhook (https://five656.onrender.com)

# ОПЦИОНАЛЬНЫЕ (с дефолтами)
BOT_MODE=webhook         # webhook (prod) | polling (dev)
LOCK_WAIT_SECONDS=60     # Время ожидания lock перед PASSIVE
LOCK_MODE=wait_then_passive  # Режим fallback
PASSIVE_MODE=REJECT      # REJECT (instant ack) | HOLD (queue until ACTIVE)
```

### Environment Variables (Forbidden)
Эти переменные НЕ должны использоваться (архитектурный долг):
- ❌ `USE_PTB` — legacy, только aiogram
- ❌ `POLLING_MODE` — используйте `BOT_MODE`
- ❌ `LOCAL_LOCK_FILE` — только PostgreSQL advisory lock в проде

### Invariants (Железобетонные правила)
1. **Один entrypoint**: `main_render.py` — единственный файл для Render `start` команды
2. **Один поток webhook**: Telegram → `/webhook` → UpdateQueueManager → Dispatcher (никаких параллельных обработчиков)
3. **Один lock mechanism**: PostgreSQL advisory lock (двухпараметрный: classid+objid, signed int32)
4. **Один DatabaseService**: `app/database/services.py` (запрет прямых psycopg2 импортов в handlers)
5. **Fast-ack всегда**: callback_query получает `answer_callback_query()` до любой бизнес-логики
6. **PASSIVE не модифицирует**: В PASSIVE режиме запрещены write operations (БД/webhook/KIE API)
7. **Логи структурные**: JSON-friendly форматирование, теги `[LOCK]`, `[WEBHOOK]`, `[QUEUE]`, rate-limit для повторов
8. **Migrations идемпотентны**: `IF NOT EXISTS` для всех DDL операций
9. **Decimal → float**: Все PostgreSQL EXTRACT(EPOCH) конвертируются в float для JSON
10. **Нет wildcard imports**: Запрет `from module import *` (explicit imports только)

## User Scenarios (S0-SN)

### S0: Health Check
```bash
curl https://five656.onrender.com/health
# Ожидаемый ответ: 200 OK
# JSON: {"status": "ok", "uptime": int, "active": bool, "lock_state": str, ...}
```

### S1: Bot Responsive (ACTIVE)
```
User → /start → Bot responds with main menu (< 3s)
User → click "Создать изображение" → Bot shows model selection
```

### S2: Storage Accessible
```bash
# DatabaseService может читать/писать
User → генерация → запись в jobs таблицу → успех
Admin → /admin → чтение user_balances → показ статистики
```

### S3: PASSIVE Graceful (NEW)
```
User → /start → Bot responds (whitelist) (< 1s)
User → click "Создать изображение" → "⏸️ Сервис обновляется" (instant)
```

## Ограничения платформы

### Render
- Webhook timeout: 30 секунд (поэтому fast-ack обязателен)
- Free tier: 15 минут inactivity → sleep (но webhook держит активным)
- Environment variables: обновляются только при redeploy

### Telegram Bot API
- Callback query TTL: ~30 секунд до "вечной крутилки"
- Webhook retry: 24 часа с экспоненциальным backoff (поэтому 200 OK всегда)
- Update dedupe: update_id должен расти монотонно

### PostgreSQL (Render)
- Advisory lock: session-level (соединение держится открытым весь runtime)
- OID type: unsigned int32 (0..2^32-1), но advisory lock использует signed int32 (-2^31..2^31-1)
- Connection pool: pgbouncer может сбрасывать session state (не используем pgbouncer для lock connection)

## Forbidden Patterns (Запрещено в коде)

### Дубликаты entrypoint
❌ Несколько файлов с `if __name__ == "__main__"` запускающих webhook
❌ Параллельные реализации lock mechanism
❌ Дублирующие route handlers (`@dp.message()` для одного паттерна в разных файлах)

### Wildcard imports
❌ `from telebot import *`
❌ `from app.handlers import *`

### Direct DB access в handlers
❌ `import psycopg2` в handler файлах (только через DatabaseService)

### Блокирующий код в async контексте
❌ `time.sleep()` в async функциях (используйте `asyncio.sleep()`)
❌ `requests.get()` в handlers (используйте `aiohttp`)

### Unsigned int в advisory lock
❌ Передача значений > 2147483647 в `pg_try_advisory_lock()` (требуется signed int32)

## Expected Log Patterns (Нормальная работа)

### ACTIVE mode startup
```
[LOCK_CONTROLLER] Attempting to acquire lock...
[LOCK_CONTROLLER] ✅ Lock acquired immediately | instance=<uuid>
[WEBHOOK_ACTIVE] ✅ Webhook ensured on ACTIVE instance
[DB] ✅ DatabaseService initialized
```

### PASSIVE mode operation
```
[LOCK_CONTROLLER] Lock held by another instance, entering PASSIVE mode
[PASSIVE_REJECT] ⏸️ Rejecting update (not in whitelist)
```

### Lock transition (takeover)
```
[LOCK] 🔴 Detected STALE lock (idle 312s, heartbeat age 327s), taking over
[LOCK] ✅ Successfully TOOK OVER stale lock
```

### Webhook queue processing
```
[QUEUE] Worker 0 started
[WEBHOOK] Enqueued update_id=123456 (queue_depth=1)
[QUEUE] Processing update_id=123456
```

## Forbidden Log Patterns (Ошибки)

### P0 (Блокирует функционал)
❌ `TypeError: Object of type Decimal is not JSON serializable`
❌ `function pg_try_advisory_lock(integer, bigint) does not exist`
❌ `psycopg2.errors.NumericValueOutOfRange: OID out of range`
❌ `Error handling request` (в aiohttp.server с Traceback)

### P1 (Спам/деградация)
❌ `[LOCK] Lock held by another instance` повторяется > 1 раз в 30 секунд (должен быть rate-limit)
❌ `asyncio.Queue` full → drops > 5% updates
❌ Webhook retries с 5xx response

## Release Checklist

Перед каждым деплоем:
1. ✅ `make firebreak` — verify_truth + syntax check
2. ✅ `pytest tests/test_render_singleton_lock.py` — unit tests
3. ✅ `git push origin main` → Render auto-deploy
4. ⏳ Wait 2-3 minutes → `python3 smoke_test.py --url https://five656.onrender.com`
5. ⏳ Wait 10 minutes → `make deploy-check` (0 ERROR в логах)
6. ⏳ Tag stable: `git tag stable-firebreak-N` (только если все зелёное)

## Версионирование

- **stable-firebreak-N**: Production-ready tags (все gates зелёные)
- **main**: Development branch (может быть красным во время FIREBREAK)
- **quarantine/legacy-YYYYMMDD**: Архивные дубликаты/deprecated код

---
**Последнее обновление**: 2026-01-13  
**Статус**: FIREBREAK MODE — стабилизация перед расширением функционала
