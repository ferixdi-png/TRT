# ✅ Z-IMAGE ATOMIC DELIVERY LOCK - FINAL

## Что изменилось в v2:

### Проблема v1:
- `delivered_at` выставлялся **ДО** реальной отправки
- Нет защиты от race condition между callback + polling
- Нет защиты от дублей при deploy overlap (ACTIVE + PASSIVE)

### Решение v2: Atomic Delivery Lock

#### 1. Миграция БД (migrations/009_add_delivering_at.sql)
```sql
ALTER TABLE generation_jobs ADD COLUMN delivering_at TIMESTAMP;
CREATE INDEX idx_jobs_delivery_lock ON generation_jobs(...) WHERE delivered_at IS NULL;
```

#### 2. Storage методы (app/storage/pg_storage.py)

**try_acquire_delivery_lock(task_id):**
```sql
UPDATE generation_jobs
SET delivering_at = NOW()
WHERE (external_task_id = $1 OR job_id = $1)
  AND delivered_at IS NULL
  AND (delivering_at IS NULL OR delivering_at < NOW() - INTERVAL '5 minutes')
RETURNING *
```
- Возвращает job dict если выиграл гонку
- Возвращает None если уже delivered или delivering

**mark_delivered(task_id, success=True, error=None):**
```sql
-- Success:
UPDATE ... SET delivered_at=NOW(), delivering_at=NULL WHERE ...

-- Failure:
UPDATE ... SET delivering_at=NULL WHERE ...  -- Allow retry
```

#### 3. Callback Handler (main_render.py)

**Старая логика (v1):**
```python
if job.get('delivered_at'):
    return  # Skip

await _deliver_result_to_telegram(...)
await storage.update_job_status(..., delivered=True)  # ❌ До отправки!
```

**Новая логика (v2):**
```python
# Atomic lock
lock_job = await storage.try_acquire_delivery_lock(task_id)
if not lock_job:
    logger.info("[DELIVER_LOCK_SKIP]")
    return

logger.info("[DELIVER_LOCK_WIN]")

try:
    await _deliver_result_to_telegram(...)
    await storage.mark_delivered(task_id, success=True)  # ✅ После отправки!
except Exception as e:
    await storage.mark_delivered(task_id, success=False, error=str(e))
```

#### 4. Polling Loop (app/kie/generator.py)

**Идентичная логика:**
```python
lock_job = await storage.try_acquire_delivery_lock(task_id)
if not lock_job:
    logger.info("[POLL_LOCK_SKIP]")
    return {..., 'already_delivered': True}

logger.info("[POLL_LOCK_WIN]")
# Deliver + mark_delivered
```

## Защита от сценариев:

### Сценарий 1: Callback + Polling (нормальная работа)
```
T1: Callback arrive → try_acquire_lock() → WIN → delivering
T2: Polling check → try_acquire_lock() → SKIP (delivering_at != NULL)
T3: Callback → deliver OK → mark_delivered(success=True)
T4: Polling check → try_acquire_lock() → SKIP (delivered_at != NULL)
```
**Результат:** 1 отправка

### Сценарий 2: Deploy Overlap (ACTIVE + PASSIVE)
```
T1: OLD instance PASSIVE: callback → try_acquire_lock() → WIN → delivering
T2: NEW instance ACTIVE: callback (retry) → try_acquire_lock() → SKIP
T3: OLD instance → deliver OK → mark_delivered
```
**Результат:** 1 отправка (PASSIVE доставил)

### Сценарий 3: Retry Callback (Kie.ai повторный вызов)
```
T1: Callback #1 → lock WIN → deliver OK → mark_delivered
T2: Callback #2 (retry) → lock SKIP (delivered_at != NULL)
```
**Результат:** 1 отправка

### Сценарий 4: Delivery Failed (network error)
```
T1: Callback → lock WIN → deliver FAIL → mark_delivered(success=False)
    → delivering_at = NULL (released)
T2: Polling → lock WIN (delivered_at still NULL) → deliver OK → mark_delivered(success=True)
```
**Результат:** Retry успешен

### Сценарий 5: Stale Lock (процесс умер во время delivery)
```
T1: Callback → lock WIN → process crash (delivering_at = T1)
T2: (5 minutes later) Polling → lock WIN (delivering_at < NOW - 5min) → deliver OK
```
**Результат:** Автоматический recovery

## Логи (новые теги):

```
[corr] [DELIVER_LOCK_WIN] Won delivery race
[corr] [DELIVER_LOCK_SKIP] Already delivered or delivering
[corr] [POLL_LOCK_WIN] Won delivery race  
[corr] [POLL_LOCK_SKIP] Already delivered or delivering
[corr] [MARK_DELIVERED] job_id=XXX (после успешной отправки)
```

## Checklist:

- [x] Миграция 009_add_delivering_at.sql
- [x] Storage: try_acquire_delivery_lock()
- [x] Storage: mark_delivered()
- [x] Callback: lock → deliver → mark
- [x] Polling: lock → deliver → mark
- [x] Логи DELIVER_LOCK_WIN/SKIP
- [x] PASSIVE mode не блокирует callbacks
- [x] Compile check успешен

## Deployment:

```bash
git add migrations/009_add_delivering_at.sql app/storage/pg_storage.py main_render.py app/kie/generator.py Z_IMAGE_E2E_COMPLETE.md
git commit -m "feat: atomic delivery lock for z-image (v2)

Prevents race conditions and duplicates:
- Added delivering_at column + atomic lock mechanism
- Callback and polling compete for delivery via try_acquire_delivery_lock()
- delivered_at set AFTER successful send (not before)
- PASSIVE mode processes callbacks (not blocked by active_state)
- Stale lock recovery (5min timeout)

Protects against: callback+polling, ACTIVE+PASSIVE, retry callbacks, network failures"

git push origin main
```

## Проверка на Render:

1. Дёрнуть Z-Image генерацию
2. Смотреть логи:
   - `[DELIVER_LOCK_WIN]` - кто-то один выиграл
   - `[DELIVER_LOCK_SKIP]` - остальные пропустили
   - `[MARK_DELIVERED]` - после успешной отправки
3. Retry callback 2-3 раза → должно быть `[DELIVER_LOCK_SKIP]`
4. Deploy overlap → не должно быть дублей

## Файлы:

- `migrations/009_add_delivering_at.sql` (NEW)
- `app/storage/pg_storage.py` (MODIFIED: +80 lines)
- `main_render.py` (MODIFIED: callback handler)
- `app/kie/generator.py` (MODIFIED: polling loop)
