# Monitoring & Observability

## P0 Telemetry Infrastructure (Cycle 9)

**Status**: ✅ INTEGRATED (2026-01-13)

### Цель
Сделать продукт **инструментируемым** — любую проблему можно диагностировать по логам за 60 секунд без участия разработчика.

### Компоненты

#### 1. Telemetry Middleware ✅
- **Файл**: `app/telemetry/telemetry_helpers.py`
- **Регистрация**: `main_render.py:259` - `dp.update.middleware(TelemetryMiddleware())`
- **Функция**: Автоматически добавляет `correlation_id` (cid) и `bot_state` ко всем updates
- **События**:
  - `UPDATE_RECEIVED` - каждый webhook
  - `DISPATCH_OK` - успешная обработка
  - `DISPATCH_FAIL` - ошибка обработки

#### 2. Logging Contract ✅
- **Файл**: `app/telemetry/logging_contract.py`
- **Функция**: `log_event(name, correlation_id, ...)` - unified structured logging
- **Формат**: JSON line (одна строка = одно событие)
- **Поля**: 50+ опциональных (user_id, chat_id, screen_id, button_id, reason_code, latency_ms, etc.)
- **PII Safety**: Автоматический hash для user_id/chat_id (8-char SHA256)

#### 3. UI Registry (SSOT) ✅
- **Файл**: `app/telemetry/ui_registry.py`
- **Screens**: 11 enum значений (MAIN_MENU, CATEGORY_PICK, MODEL_PICK, PARAMS_FORM, CONFIRM, PROCESSING, RESULT, ...)
- **Buttons**: 15+ enum значений (CAT_IMAGE, CAT_VIDEO, MODEL_ZIMAGE, CONFIRM_RUN, BACK, CANCEL, ...)
- **Validation**: `UIMap.is_valid_button_on_screen()` - предотвращает невозможные комбинации

#### 4. Reason Codes (Semantic Failure Classification) ✅
- **Enum**: `ReasonCode` (14 значений)
- **Примеры**:
  - `PASSIVE_REJECT` - bot instance не ACTIVE (ждет другого instance)
  - `UNKNOWN_ACTION` - callback_data malformed
  - `STATE_MISMATCH` - FSM state неправильный (пользователь на неожиданном экране)
  - `VALIDATION_FAILED` - параметр не соответствует schema
  - `DOWNSTREAM_TIMEOUT` - KIE.ai или webhook timeout
  - `DB_ERROR` - ошибка storage layer
  - `SUCCESS`, `NOOP` - нормальные outcomes

#### 5. Admin Debug Panel ✅
- **Handler**: `app/handlers/debug_handler.py`
- **Команда**: `/debug` (только admin)
- **Функции**:
  - Show bot_state (ACTIVE/PASSIVE)
  - Last 10 events summary
  - Last correlation_id for log search
  - Enable DEBUG logs for 30 minutes
- **Регистрация**: `main_render.py:263` - `dp.include_router(debug_router)`

### Event Chain Example

Успешное нажатие кнопки "Картинки":
```json
{"ts": "2026-01-13T10:30:45Z", "name": "UPDATE_RECEIVED", "cid": "a1b2c3d4", "event_type": "callback_query", "update_id": 12345}
{"ts": "2026-01-13T10:30:45Z", "name": "CALLBACK_RECEIVED", "cid": "a1b2c3d4", "user_hash": "hash_xxx", "payload": "cat:image"}
{"ts": "2026-01-13T10:30:45Z", "name": "CALLBACK_ROUTED", "cid": "a1b2c3d4", "handler": "category_cb", "button_id": "CAT_IMAGE"}
{"ts": "2026-01-13T10:30:46Z", "name": "CALLBACK_ACCEPTED", "cid": "a1b2c3d4", "screen_id": "CATEGORY_PICK", "result": "accepted"}
{"ts": "2026-01-13T10:30:46Z", "name": "UI_RENDER", "cid": "a1b2c3d4", "screen_id": "CATEGORY_PICK", "buttons_count": 5}
{"ts": "2026-01-13T10:30:46Z", "name": "DISPATCH_OK", "cid": "a1b2c3d4"}
```

Отклоненная кнопка (STATE_MISMATCH):
```json
{"ts": "2026-01-13T10:31:00Z", "name": "UPDATE_RECEIVED", "cid": "b2c3d4e5", "event_type": "callback_query"}
{"ts": "2026-01-13T10:31:00Z", "name": "CALLBACK_RECEIVED", "cid": "b2c3d4e5", "payload": "confirm"}
{"ts": "2026-01-13T10:31:00Z", "name": "CALLBACK_ROUTED", "cid": "b2c3d4e5", "handler": "confirm_cb"}
{"ts": "2026-01-13T10:31:00Z", "name": "CALLBACK_REJECTED", "cid": "b2c3d4e5", "reason_code": "STATE_MISMATCH", "reason_text": "Expected PARAMS_FORM, got MAIN_MENU"}
{"ts": "2026-01-13T10:31:00Z", "name": "ANSWER_CALLBACK_QUERY", "cid": "b2c3d4e5", "text": "Кнопка устарела, используйте /start"}
```

### Integration Status

| Handler | Status | Events Logged |
|---------|--------|---------------|
| `main_render.py` (middleware) | ✅ DONE | UPDATE_RECEIVED, DISPATCH_OK/FAIL |
| `/debug` command | ✅ DONE | Admin diagnostics |
| `flow.py::start_cmd` | ✅ DONE | COMMAND_START |
| `flow.py::main_menu_cb` | ✅ DONE | CALLBACK_* chain |
| `flow.py::category_cb` | ✅ DONE | CALLBACK_* chain |
| `flow.py::model_cb` | ✅ DONE | CALLBACK_* chain |
| `z_image.py` | 🔄 TODO | CALLBACK_* chain |
| `balance.py` | 🔄 TODO | CALLBACK_* chain |
| `history.py` | 🔄 TODO | CALLBACK_* chain |

### Telemetry Contract Checklist (Cycle 10)

**Required Event Names:**
- `UPDATE_RECEIVED` - every webhook/update
- `CALLBACK_RECEIVED` - every callback query
- `COMMAND_RECEIVED` - every command
- `CALLBACK_ROUTED` - callback routed to handler
- `CALLBACK_ACCEPTED` - callback processed successfully
- `CALLBACK_REJECTED` - callback rejected (with reason_code)
- `UI_RENDER` - screen rendered
- `DISPATCH_OK` - successful dispatch
- `TASK_CREATED` - generation task created
- `TASK_COMPLETED` - generation task completed

**Required Fields per Event:**
- `cid` (correlation ID) - **MANDATORY** for all events
- `update_id` - for UPDATE_RECEIVED (from Telegram)
- `callback_id` - for CALLBACK_RECEIVED (from CallbackQuery.id)
- `user_id` - user identifier (hashed in production)
- `bot_state` - ACTIVE or PASSIVE
- `screen_id` - for UI_RENDER events
- `reason_code` - for CALLBACK_REJECTED (PASSIVE_REJECT, VALIDATION_FAIL, UNKNOWN_CALLBACK, etc.)
- `handler` - for CALLBACK_ROUTED events

**Standard Rejection Reasons:**
- `PASSIVE_REJECT` - bot is in PASSIVE mode during deploy overlap
- `VALIDATION_FAIL` - parameter validation failed
- `UNKNOWN_CALLBACK` - no handler found for callback_data
- `STATE_MISMATCH` - FSM state mismatch
- `BALANCE_INSUFFICIENT` - user balance too low
- `MODEL_DISABLED` - model is disabled
- `RATE_LIMIT` - user rate limit exceeded

### 60-Second Diagnosis Workflow

**Scenario**: "Кнопка не работает"

1. User reports issue
2. Admin: `/debug` → click "Show Last CID" → see `cid=a1b2c3d4`
3. Go to Render logs, search: `cid=a1b2c3d4`
4. See chain:
   ```
   CALLBACK_RECEIVED ✅
   CALLBACK_ROUTED ✅
   CALLBACK_REJECTED reason_code=PASSIVE_REJECT
   ```
5. **Diagnosis**: "Bot not ACTIVE (другой instance обрабатывает). Retry через 10 сек."

**Time**: < 60 seconds from report to root cause.

## Log Analysis

### Forbidden Log Patterns (from product/truth.yaml)

Эти паттерны указывают на баги и **НЕ должны появляться** в production логах:

```python
forbidden_errors = [
    "Decimal.*is not JSON serializable",  # P0: Fixed in Cycle 1
    "OID.*out of range",                   # P0: Advisory lock overflow
    "Error handling request",              # P1: Unhandled exception
    "Lock acquisition failed",             # P1: Lock contention
    "Queue full",                          # P2: Overload
    "Database connection lost",            # P0: Connection pool issue
    "Webhook timeout",                     # P1: Slow response (> 500ms)
    "Migration.*failed",                   # P0: DB schema corruption
    "heartbeat=none.*idle>30",            # P0: Stale lock without heartbeat (CYCLE 8)
]
```

**CYCLE 8 Update**: Added `heartbeat=none` detection after production incident where migration 007 was skipped due to duplicate numbering.

Если любой из этих паттернов появляется → **IMMEDIATE ACTION REQUIRED**.

### Rate-Limited Log Patterns

Эти паттерны допустимы, но не чаще чем 1 раз / 30 секунд:

```python
rate_limited_patterns = [
    "Duplicate update_id",    # OK: Telegram retry
    "Insufficient balance",   # OK: User попытался сгенерировать без баланса
    "Model not found",        # OK: User выбрал несуществующую модель
]
```

Если чаще → возможно атака или баг.

## Log Levels

```python
logging.basicConfig(
    level=logging.INFO,  # Production default
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

**Levels**:
- `DEBUG`: Только для development (не в production!)
- `INFO`: Нормальные операции (start, webhook, generation completed)
- `WARNING`: Ожидаемые ошибки (insufficient balance, duplicate update)
- `ERROR`: Неожиданные ошибки (API timeout, database error)
- `CRITICAL`: Фатальные ошибки (startup failure, lock lost)

## Structured Logging Tags

```python
logger.info("User balance checked", extra={
    "user_id": user_id,
    "balance": balance,
    "operation": "check_balance",
    "duration_ms": 45
})
```

**Standard tags**:
- `user_id`: Telegram user ID
- `update_id`: Telegram update ID (для dedupe)
- `operation`: Тип операции (`webhook`, `generation`, `payment`)
- `duration_ms`: Время выполнения (для performance tracking)
- `error_type`: Класс ошибки (для группировки)

## Key Metrics to Monitor

### Uptime & Availability
- **Target**: 99.5% uptime (допустимый downtime: 3.6 hours/month)
- **Check**: `/health` endpoint every 60 seconds
- **Alert**: If `/health` fails 3 consecutive times → notify

### Response Time
- **Target**: P50 < 300ms, P95 < 800ms, P99 < 2s
- **Measure**: Webhook response time (from Telegram POST to 200 OK)
- **Alert**: If P95 > 1s for 5 minutes → investigate

### Error Rate
- **Target**: < 0.1% of requests (< 1 error / 1000 requests)
- **Measure**: Count ERROR/CRITICAL logs per 10 minutes
- **Alert**: If > 10 errors in 10 minutes → notify

### Queue Depth
- **Target**: < 50 updates in queue
- **Measure**: `queue_size` in `/health` response
- **Alert**: If > 80 for 5 minutes → possible overload

### Database Pool
- **Target**: < 15 active connections (out of 20 max)
- **Measure**: PostgreSQL `pg_stat_activity`
- **Alert**: If > 18 for 5 minutes → connection leak

### Lock Heartbeat (CYCLE 8 update)
- **Target**: Heartbeat every 15 seconds, stale detection at 30s idle
- **Measure**: `heartbeat_age` in `/health` response
- **Alert**: If `heartbeat=none` OR `heartbeat_age > 45s` → lock table migration missing
- **Fix**: Ensure migration 007_lock_heartbeat.sql applied (CYCLE 8: fixed duplicate migration number)

**Lock Failover Metrics** (from production logs):
- Time to detect stale lock: 30s (STALE_IDLE_SECONDS)
- Grace period after termination: 3s (LOCK_RELEASE_WAIT_SECONDS)
- Total time-to-ACTIVE: ~33s (down from 53s pre-CYCLE 8)
- Heartbeat interval: 15s (ensures 2 updates within stale window)
@@**Health Endpoint Lock Fields** (`GET /health`):
@@- `lock_state`: "ACTIVE" or "PASSIVE"
@@- `lock_holder_pid`: Process ID holding the advisory lock
@@- `lock_idle_duration`: Seconds since last state change (null if no holder)
@@- `lock_heartbeat_age`: Seconds since last heartbeat update (null if table unavailable)
@@- `lock_takeover_event`: Last lock takeover details (null if never occurred)
@@
@@**Diagnostic Pattern** (when heartbeat is not working):
@@1. Check `/health` → `lock_heartbeat_age: null`
@@2. Check logs → "⚠️ Heartbeat table unavailable (migration 007 not applied?)"
@@3. Verify migration: `psql -c "SELECT * FROM lock_heartbeat LIMIT 1"`
@@4. Apply if missing: Run migration 007_lock_heartbeat.sql manually
@@

## Render Dashboard Metrics

### CPU Usage
- **Normal**: 10-30%
- **Warning**: > 60% sustained
- **Critical**: > 90% (throttling likely)

### Memory Usage
- **Normal**: 100-300 MB
- **Warning**: > 400 MB
- **Critical**: > 480 MB (512 MB instance → OOM risk)

### Requests/Minute
- **Normal**: 5-50 requests/minute
- **Warning**: > 100 requests/minute (traffic spike)
- **Critical**: > 200 requests/minute (possible attack)

## Alerting Strategy

### Tier 1: Auto-fix
- Duplicate update_id → dedupe logic
- Insufficient balance → reject gracefully
- Queue full → reject with 429 status

### Tier 2: Warning (log, no action)
- Slow response (300-800ms) → log with WARNING
- Model not found → log + notify user
- External API timeout → retry with backoff

### Tier 3: Alert (notify on-call)
- `/health` fails 3x → page on-call
- Error rate > threshold → page on-call
- Database connection lost → page on-call
- Lock lost unexpectedly → page on-call

### Tier 4: Critical (immediate escalation)
- Any forbidden log pattern → escalate immediately
- OOM kill → restart + escalate
- Startup failure → escalate immediately

## Debug Tools

### Check Render logs in real-time
```bash
# Install Render CLI
npm install -g render

# Tail logs
render logs --service=<service-id> --tail
```

### Query database for diagnostics
```sql
-- Check lock state
SELECT * FROM lock_heartbeat;

-- Check recent jobs
SELECT id, user_id, status, created_at, completed_at
FROM jobs
ORDER BY created_at DESC
LIMIT 10;

-- Check recent transactions
SELECT user_id, amount, type, description, created_at
FROM transactions
ORDER BY created_at DESC
LIMIT 20;
```

### Test webhook locally (dev container)
```bash
# Start bot locally
python main_render.py

# In another terminal, send test update
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 999999,
    "message": {
      "message_id": 1,
      "from": {"id": 123, "is_bot": false, "first_name": "Test"},
      "chat": {"id": 123, "type": "private"},
      "text": "/start"
    }
  }'
```

## Dashboards (Future)

Если проект масштабируется:
- **Grafana**: CPU, memory, response time, error rate
- **Sentry**: Error tracking, stack traces, user context
- **DataDog**: Distributed tracing, APM
- **Custom dashboard**: Balance trends, generation stats, revenue

Пока (small scale): Render Dashboard + manual log analysis достаточно.

## Log Retention

- **Render logs**: 7 days (free tier)
- **Database logs**: 30 days (migrations, critical operations)
- **Transaction logs**: Infinite (legal requirement for payments)

## Privacy & Compliance

- ❌ Never log TELEGRAM_BOT_TOKEN
- ❌ Never log KIE_API_KEY
- ❌ Never log user prompts (unless consent)
- ✅ Log user_id (needed for support)
- ✅ Log transaction amounts (legal requirement)
- ✅ Mask sensitive data (e.g., `balance=***` if needed)
