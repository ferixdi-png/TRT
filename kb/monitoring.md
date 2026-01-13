# Monitoring & Observability

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
]
```

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

### Lock Heartbeat
- **Target**: Heartbeat every 30 seconds
- **Measure**: `last_heartbeat` in `lock_heartbeat` table
- **Alert**: If > 60 seconds since last heartbeat → stale lock

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
