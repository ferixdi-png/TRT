# ITERATION 1 COMPLETE - Production Foundation

## 🎯 Выполнено

### 1. ✅ Database Schema Consolidation

**Создано**:
- `migrations/005_consolidate_schema.sql` - Полная консолидация схемы

**Ключевые изменения**:
- ❌ Удалено: `generation_jobs` (legacy table)
- ✅ Создано: Unified `jobs` table со всеми полями:
  - `id` (BIGSERIAL PRIMARY KEY)
  - `user_id` → `users(user_id)` (FK enforced)
  - `kie_task_id` (для связи с KIE API)
  - `idempotency_key` ← **UNIQUE index** (prevents duplicates)
  - `chat_id` (для доставки результата в Telegram)
  - `delivered_at` (подтверждение доставки)
  - `status` CHECK constraint ('draft', 'pending', 'running', 'done', 'failed', 'canceled')

**Инварианты зафиксированы**:
```sql
-- Users must exist before jobs
FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE

-- Idempotency enforced
CREATE UNIQUE INDEX idx_jobs_idempotency ON jobs(idempotency_key);

-- Balance constraints
CHECK (balance_rub >= 0)
CHECK (balance_rub + hold_rub >= 0)
```

---

### 2. ✅ JobServiceV2 - Atomic Operations

**Файл**: `app/services/job_service_v2.py`

**Ключевые методы**:

#### `create_job_atomic()`
```python
async with db.transaction():
    # 1. Check idempotency (duplicate safety)
    # 2. Validate user exists (FK enforcement)
    # 3. Hold balance (if paid model)
    # 4. Insert job (status='pending')
    # 5. Return job dict
```

**Гарантии**:
- ✅ Атомарность (rollback при ошибке)
- ✅ Идемпотентность (дубликаты возвращают existing job)
- ✅ FK validation (user exists before job)
- ✅ Balance hold (prevents double-spend)

#### `update_from_callback()`
```python
async with db.transaction():
    # 1. Update job status
    # 2. Release hold + charge balance (if done)
    # 3. OR just release hold (if failed)
    # 4. Log operation to ledger
```

**Lifecycle**:
```
pending → running → done/failed
  ↓        ↓         ↓
hold    (wait)   charge/release
```

---

### 3. ✅ StrictKIEClient - Единый источник правды

**Файл**: `app/integrations/strict_kie_client.py`

**Ключевые особенности**:

1. **Validation BEFORE API call**:
```python
def _validate_model(model_id):
    if model_id not in SOURCE_OF_TRUTH['models']:
        raise KIEValidationError("Unknown model")

def _validate_inputs(model_id, params):
    schema = SOURCE_OF_TRUTH['models'][model_id]['input_schema']
    # Validate against schema
```

2. **Strict contract**:
```python
async def create_task(...) -> str:
    """Returns: task_id (raises on error, NO silent failures)"""
    
async def get_task_status(task_id) -> Dict:
    """Returns: {state, resultJson, failMsg, ...}"""
```

3. **Retry with backoff**:
- Network errors: retry
- 5xx errors: retry
- 429 rate limit: retry with extra delay
- 4xx errors: NO retry (immediate fail)

4. **Detailed logging**:
```python
logger.info("[KIE_REQUEST] POST /createTask model=... inputs=...")
logger.debug("[KIE_PAYLOAD] {...}")
logger.info("[KIE_RESPONSE] task_id=...")
```

---

### 4. ✅ GenerationServiceV2 - Правильный Lifecycle

**Файл**: `app/services/generation_service_v2.py`

**CRITICAL: Job создаётся ПЕРЕД вызовом KIE API**

```python
async def create_generation():
    # PHASE 1: Create job in DB (status='pending')
    job = await job_service.create_job_atomic(...)
    
    # PHASE 2: Call KIE API
    task_id = await kie_client.create_task(..., callback_url=f"/kie-callback?job_id={job.id}")
    
    # PHASE 3: Update job with task_id (status='running')
    await job_service.update_with_kie_task(job_id, task_id, 'running')
```

**Почему это важно?**
- ✅ Job exists BEFORE callback arrives (no orphans)
- ✅ If KIE fails, job marked as failed (no money lost)
- ✅ Atomic operations (rollback on errors)

**Callback handling**:
```python
async def handle_callback(task_id, state, result_json):
    job = await job_service.get_by_task_id(task_id)
    
    if not job:
        return False  # Orphan - will be reconciled
    
    await job_service.update_from_callback(
        job_id, 
        status='done' if state == 'success' else 'failed',
        result_json=result_json
    )
    # Автоматически: release hold + charge balance
```

**Telegram delivery**:
```python
async def deliver_to_telegram(job_id, bot):
    # Retry with exponential backoff
    for attempt in range(3):
        try:
            await bot.send_message(chat_id, result)
            await job_service.mark_delivered(job_id)
            return True
        except TelegramAPIError:
            await asyncio.sleep(2 ** attempt)
```

---

## 📊 Что изменилось

### До (Legacy)
```
User → KIE API → job creation → callback → race condition
                     ↓
                  orphan callbacks
```

### После (V2)
```
User → validate → create job (pending) → KIE API → update job (running)
                     ↓                        ↓
                  hold balance           callback arrives
                     ↓                        ↓
                  job exists!            update job (done)
                                              ↓
                                         charge balance
                                              ↓
                                         deliver to TG
```

---

## 🧪 Следующие шаги (Iteration 2)

### Интеграция новых сервисов
1. Обновить `main_render.py` для использования `GenerationServiceV2`
2. Подключить `StrictKIEClient` вместо старых клиентов
3. Обновить callback handler для работы с `JobServiceV2`

### Миграция данных
1. Запустить migration 005 на production
2. Проверить миграцию существующих jobs
3. Удалить старые клиенты (kie_client.py, kie_client_sync.py, etc.)

### E2E тесты
1. Создать `tools/e2e_v2_test.py`
2. Проверить полный lifecycle:
   - Create user
   - Create FREE generation
   - Wait for callback
   - Verify result delivered
   - Check balance unchanged

---

## 🔮 Предсказание логов после деплоя

### Migration
```
[2026-01-12 12:00:00] [MIGRATION] Running 005_consolidate_schema.sql
[2026-01-12 12:00:01] [MIGRATION] Migrated 1234 jobs from generation_jobs
[2026-01-12 12:00:02] [MIGRATION] ✅ Complete: 6 core tables verified
```

### Startup
```
[2026-01-12 12:00:05] [KIE_CLIENT] ✅ Loaded SOURCE_OF_TRUTH v1.2.10 (72 models)
[2026-01-12 12:00:06] [DB] Pool created: min=2 max=10
[2026-01-12 12:00:07] [SERVER] Webhook ready: https://your-app.render.com/webhook/...
```

### First Generation (FREE model)
```
[2026-01-12 12:05:00] [GEN_CREATE] user=12345 model=wan/2-5-standard price=0.00
[2026-01-12 12:05:01] [JOB_CREATE] id=567 user=12345 status=pending
[2026-01-12 12:05:02] [KIE_REQUEST] POST /createTask model=wan/2-5-standard
[2026-01-12 12:05:03] [KIE_RESPONSE] task_id=xyz789
[2026-01-12 12:05:04] [JOB_UPDATE] id=567 task=xyz789 status=running
[2026-01-12 12:05:05] [GEN_SUCCESS] job=567 task=xyz789 callback=.../kie-callback?job_id=567

... 30 seconds later ...

[2026-01-12 12:05:35] [CALLBACK] task=xyz789 state=success
[2026-01-12 12:05:36] [JOB_CALLBACK] id=567 status=done
[2026-01-12 12:05:37] [BALANCE] user=12345 charged=0.00 (FREE model)
[2026-01-12 12:05:38] [TELEGRAM_SUCCESS] job=567 chat=12345 delivered=True
```

### Paid Generation (with balance)
```
[2026-01-12 12:10:00] [GEN_CREATE] user=12346 model=runway/gen-3 price=120.00
[2026-01-12 12:10:01] [JOB_CREATE] id=568 user=12346 status=pending
[2026-01-12 12:10:02] [BALANCE] user=12346 hold=120.00 (before KIE call)
[2026-01-12 12:10:03] [KIE_REQUEST] POST /createTask model=runway/gen-3
[2026-01-12 12:10:04] [KIE_RESPONSE] task_id=abc123
[2026-01-12 12:10:05] [JOB_UPDATE] id=568 task=abc123 status=running

... callback arrives ...

[2026-01-12 12:15:00] [CALLBACK] task=abc123 state=success
[2026-01-12 12:15:01] [JOB_CALLBACK] id=568 status=done
[2026-01-12 12:15:02] [BALANCE] user=12346 charged=120.00 hold_released=120.00
[2026-01-12 12:15:03] [TELEGRAM_SUCCESS] job=568 chat=12346 delivered=True
```

### Error case (KIE API fails)
```
[2026-01-12 12:20:00] [GEN_CREATE] user=12347 model=test/model price=10.00
[2026-01-12 12:20:01] [JOB_CREATE] id=569 user=12347 status=pending
[2026-01-12 12:20:02] [BALANCE] user=12347 hold=10.00
[2026-01-12 12:20:03] [KIE_REQUEST] POST /createTask model=test/model
[2026-01-12 12:20:04] [KIE_ERROR] Client error 422: Model not found
[2026-01-12 12:20:05] [GEN_ERROR] job=569 KIE API error: Model not found
[2026-01-12 12:20:06] [JOB_CALLBACK] id=569 status=failed
[2026-01-12 12:20:07] [BALANCE] user=12347 refunded=10.00 (hold released)
```

---

## ✅ Success Criteria (Iteration 1)

- ✅ Единая DB схема (`jobs` table)
- ✅ Идемпотентность (UNIQUE на idempotency_key)
- ✅ Атомарные операции (transactions)
- ✅ FK constraints (users → jobs)
- ✅ Job создаётся ДО KIE API (no orphans)
- ✅ Balance hold/release/charge atomic
- ✅ Строгая валидация (SOURCE_OF_TRUTH)
- ✅ Подробное логирование

**READY FOR ITERATION 2**: Интеграция и тестирование
