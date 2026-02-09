# Job Pipeline: Generation Lifecycle
## TRT AI Generation System

---

## Job States (Canonical)

```
┌─────────────┐
│ create_start│ ← Job submitted
└──────┬──────┘
       │
┌──────▼──────┐
│ task_created│ ← KIE API accepted
└──────┬──────┘
       │
┌──────▼──────┐
│   queued    │ ← In provider queue
└──────┬──────┘
       │
┌──────▼──────┐
│   waiting   │ ← Processing (generating)
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
┌──▼───┐ ┌─▼────┐
│success│ │failed│
└──┬───┘ └──────┘
   │
┌──▼────────────┐
│result_validated│ ← URLs verified
└──────┬────────┘
       │
┌──────▼──────┐
│  tg_deliver │ ← Sent to Telegram
└─────────────┘
```

---

## State Machine

| State | Canonical | Description |
|-------|-----------|-------------|
| `pending` | `queued` | Initial state |
| `queued`, `queuing` | `queued` | In queue |
| `waiting`, `processing`, `running`, `generating` | `waiting` | In progress |
| `success`, `completed`, `succeeded` | `success` | Done |
| `failed`, `fail`, `error` | `failed` | Error |
| `canceled`, `cancelled` | `canceled` | User cancelled |

Source: `app/generations/state_machine.py`

---

## Timeouts & Retries

| Parameter | ENV Variable | Default |
|-----------|--------------|---------|
| Waiting timeout | `KIE_WAITING_TIMEOUT_SECONDS` | 120s |
| Max retries | `KIE_WAITING_MAX_RETRIES` | 2 |
| Poll interval | `KIE_POLL_PROGRESS_INTERVAL_SECONDS` | 15s |
| Watchdog TTL | `KIE_WATCHDOG_TTL_SECONDS` | 86400s |
| Image timeout | `KIE_TIMEOUT_IMAGE` | 180s |
| Video timeout | `KIE_TIMEOUT_VIDEO` | 600s |
| Audio timeout | `KIE_TIMEOUT_AUDIO` | 180s |

Source: `app/generations/universal_engine.py`

---

## Idempotency

### Balance Charging
- **Method**: `charge_balance_once(user_id, amount, task_id, sku_id, model_id)`
- **Deduplication**: By `task_id`
- **DB Lock**: `FOR UPDATE` on user balance row
- **Source**: `app/storage/postgres_storage.py`

### Free Generation Consumption
- **Method**: `consume_free_generation_once(user_id, task_id, sku_id)`
- **Deduplication**: By `task_id`
- **Source**: `app/storage/postgres_storage.py`

### Job Creation
- **Method**: `add_generation_job(job_id, ...)`
- **Deduplication**: By `job_id` (unique constraint)

---

## Parallel Request Protection

### Redis Lock (if available)
```python
# Watchdog lock by prompt_hash
key = f"kie:watchdog:lock:{prompt_hash}"
acquired = await redis.set(key, token, nx=True, ex=ttl_seconds)
```

### In-flight Job Tracking
```python
# Per-user in-flight tracking
_start_inflight_jobs: Dict[int, Dict[str, Any]] = {}
```

Source: `bot_kie.py:8571-8595`

---

## Error Handling

### Provider Failure
1. Job status = `failed`
2. Error logged with `failMsg`, `failCode`
3. User notified: "⚠️ Генерация не удалась"
4. **NO charge** - balance charged only AFTER success

### Timeout
1. After `KIE_WAITING_TIMEOUT_SECONDS`
2. Retries up to `KIE_WAITING_MAX_RETRIES`
3. Final failure → user notified

### Network Error
1. Retry with exponential backoff
2. Max retries configurable
3. Final failure → graceful degradation

---

## Result Delivery

### Bot Flow
1. `run_generation()` returns `JobResult`
2. URLs normalized via `normalize_result_urls()`
3. Media sent via `send_result_file()`
4. Balance charged AFTER successful send
5. Job status updated to `delivered`

### Mini App Flow
1. Job created via `/webapp/generate`
2. Polling via `/webapp/job/{job_id}`
3. On success: `result_url` returned
4. Balance charged in background task
5. Job status = `success`

---

## Files Involved

| File | Purpose |
|------|---------|
| `app/generations/universal_engine.py` | Main engine |
| `app/generations/state_machine.py` | State normalization |
| `app/generations/telegram_sender.py` | Result delivery |
| `app/generations/media_pipeline.py` | Media processing |
| `app/storage/postgres_storage.py` | Job persistence |
| `webapp/aiohttp_handlers.py` | Mini App jobs |

---

## Monitoring

### Logs to Watch
- `KIE_SUBMIT` - Job submitted
- `KIE_CREATE` - Task created
- `TASK_CREATED` - Provider accepted
- `PROGRESS_UPDATE` - Status change
- `CHARGE_BALANCE_ONCE` - Deduction
- `DELIVERY_COMPLETE` - Result sent

### Metrics
- `record_create_latency(ms)` - Creation time
- `record_wait_latency(ms)` - Total wait time

