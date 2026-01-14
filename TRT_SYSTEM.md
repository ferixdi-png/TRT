# TRT System Specification - "How It Works"

**Version**: 1.0  
**Last Updated**: 2026-01-14  
**Maintainer**: Cursor Pro Autonomous Senior Engineer

---

## A. High-Level Architecture

### Data Flow Diagram (Text)

```
Telegram Bot API
    ↓
POST /webhook/<secret_path>
    ↓ (fast-ack: 200 OK in <200ms)
UpdateQueue.enqueue(update)
    ↓
Background Workers (3 concurrent)
    ↓
Dispatcher.feed_update(update)
    ↓
Handlers (flow, admin, balance, history, etc.)
    ↓
KIE API Integration
    ├─ createTask → task_id
    ├─ callbackUrl (webhook) OR polling (recordInfo)
    └─ result → Storage (jobs table)
    ↓
Result Delivery
    ├─ sendMedia (image/video)
    ├─ sendMessage (text/audio)
    └─ update job status (done/failed)
```

### Component Responsibilities

1. **Webhook Handler** (`main_render.py:webhook`)
   - Validates secret path + token header
   - Fast-ack: returns 200 OK immediately (<200ms target)
   - Enqueues update to `UpdateQueue` (non-blocking)
   - Deduplicates by `update_id` (in-memory cache)

2. **UpdateQueue** (`app/utils/update_queue.py`)
   - Bounded async queue (max 100 items)
   - 3 concurrent worker tasks
   - Graceful degradation: drops updates if queue full (but still acks HTTP)
   - Metrics: total_received, total_processed, total_dropped, queue_depth

3. **Workers** (`UpdateQueueManager._worker_loop`)
   - Read from queue
   - Check ACTIVE/PASSIVE state (via `ActiveState`)
   - If PASSIVE: reject update (log `PASSIVE_REJECT`) OR send ephemeral response
   - If ACTIVE: call `dp.feed_update(update)`

4. **Dispatcher** (aiogram `Dispatcher`)
   - Routes updates to handlers via middleware chain
   - Middleware order:
     1. `TelemetryMiddleware` (adds `cid`, `bot_state`, `screen_id`)
     2. `ExceptionMiddleware` (catches all unhandled exceptions)
     3. Handler routers (flow, admin, balance, etc.)
     4. `FallbackRouter` (catches unknown callbacks)

5. **Handlers** (`bot/handlers/*.py`)
   - Process user interactions (commands, callbacks, messages)
   - Update FSM state (via `FSMContext`)
   - Call KIE API for generation
   - Store results in database
   - Send responses to user

6. **Storage** (`app/database/schema.py`, `app/storage/pg_storage.py`)
   - PostgreSQL tables: users, wallets, ledger, jobs, ui_state, free_models, free_usage
   - Connection pooling (asyncpg, min=1, max=10)
   - Migrations: idempotent `CREATE TABLE IF NOT EXISTS`

7. **KIE Integration** (`app/kie/kie_gateway.py`)
   - Endpoints: `POST /api/v1/jobs/createTask`, `GET /api/v1/jobs/recordInfo?taskId=...`
   - Callback strategy: webhook URL (`/callbacks/kie`) OR polling (fallback)
   - Retry/backoff: exponential backoff for failed requests

---

## B. Runtime Modes

### BOT_MODE

**Environment Variable**: `BOT_MODE`  
**Values**: `webhook` (default), `polling`  
**Meaning**:
- `webhook`: Telegram sends updates to `/webhook/<secret_path>` (production)
- `polling`: Bot polls Telegram API for updates (development/testing)

**Default**: `webhook` (required for Render deployment)

### SINGLE_MODEL_ONLY

**Environment Variable**: `SINGLE_MODEL_ONLY`  
**Values**: `1` (true), `0` (false, default)  
**Meaning**: If `1`, only enable `z-image` model (for testing/minimal deployment)

**Default**: `0` (all models enabled)

### ACTIVE/PASSIVE Mode (Singleton Lock)

**Mechanism**: PostgreSQL advisory lock (session-level)  
**Lock Key**: Derived from `LOCK_KEY1` and `LOCK_KEY2` env vars (default: `214748364, 2`)

**States**:
- **ACTIVE**: Lock acquired → processes all updates, sends webhook to Telegram
- **PASSIVE**: Lock not acquired → returns 200 OK but does NOT process updates (acceptable only during deploy overlap)

**Acquisition Logic** (`app/locking/single_instance.py`):
1. Attempt to acquire lock with retry (exponential backoff, max 60s wait)
2. If acquired → ACTIVE mode
3. If not acquired:
   - `LOCK_MODE=wait_then_passive` (default) → PASSIVE mode
   - `LOCK_MODE=wait_then_force` → FORCE ACTIVE (risky, may cause conflicts)

**Background Retry**: If PASSIVE, background task retries lock acquisition every 60-90 seconds

**Health Check**: `/health` endpoint shows `"mode": "active" | "passive"` and `"lock_acquired": true | false`

### Worker Concurrency

**Workers**: 3 concurrent tasks (configurable via `UpdateQueueManager.num_workers`)  
**Queue Size**: 100 items max (configurable via `UpdateQueueManager.max_size`)

### Retry Loop

**KIE API Retries**: Exponential backoff (base 0.5s, max 5s, max retries 3)  
**Lock Retries**: Exponential backoff (base 0.5s, max 5s, max wait 60s)

---

## C. Critical Invariants

### 1. Fast-Ack Guarantee

**Invariant**: Webhook handler MUST return 200 OK in <200ms  
**Implementation**: 
- No blocking operations in webhook handler
- All business logic happens in background workers
- Even if queue full, return 200 OK (log warning, but ack)

**Violation**: If webhook takes >5s, Telegram will retry, causing duplicate updates

### 2. Single Active Instance

**Invariant**: Only ONE instance processes updates at a time  
**Implementation**: PostgreSQL advisory lock (session-level)  
**Enforcement**: Workers check `ActiveState.active` before processing

**Violation**: If multiple instances process same update → duplicate messages, double charges

### 3. PASSIVE Mode Behavior

**Invariant**: PASSIVE instance returns 200 OK but does NOT process updates  
**Exception**: Some updates allowed in PASSIVE (e.g., `/start`, `main_menu`, `help`)  
**Implementation**: `UpdateQueueManager._is_passive_allowed(update)` whitelist

**Acceptable Scenarios**:
- During Render deploy overlap (old instance ACTIVE, new instance PASSIVE)
- After deploy, old instance shuts down, new instance acquires lock → ACTIVE

**Unacceptable**: PASSIVE mode lasting >5 minutes (indicates stuck lock or deployment issue)

### 4. Canonical Model/Pricing Sources

**Source of Truth**: `models/KIE_SOURCE_OF_TRUTH.json`  
**Update Policy**:
- NEVER modify manually without verification
- Use `scripts/kie_sync.py --dry-run` to compare with upstream docs
- Apply changes only with `APPLY_MODEL_DIFFS=1` OR explicit admin action
- Always preserve backward-compatible aliases for model IDs

**Pricing Formula**: `RUB = KIE_USD * 2.0 * FX_RATE` (where FX_RATE from `USD_RUB_RATE` env var or fixed constant)

---

## D. Data & Storage

### Database Schema

**Connection**: PostgreSQL via `DATABASE_URL` env var  
**Pool**: asyncpg pool (min=1, max=10, timeout=60s)

### Tables

1. **users** (`app/database/schema.py:14-23`)
   - `user_id` (BIGINT PRIMARY KEY) - Telegram user ID
   - `username`, `first_name` - User info
   - `role` (TEXT) - 'user', 'admin', 'banned'
   - `locale` (TEXT) - 'ru' (default)
   - `created_at`, `last_seen_at` (TIMESTAMP)
   - `metadata` (JSONB) - Additional data

2. **wallets** (`app/database/schema.py:30-36`)
   - `user_id` (BIGINT PRIMARY KEY) - FK to users
   - `balance_rub` (NUMERIC(12,2)) - Available balance (>=0)
   - `hold_rub` (NUMERIC(12,2)) - Reserved balance (>=0)
   - `updated_at` (TIMESTAMP)
   - Constraint: `balance_rub + hold_rub >= 0`

3. **ledger** (`app/database/schema.py:41-50`)
   - `id` (BIGSERIAL PRIMARY KEY)
   - `user_id` (BIGINT) - FK to users
   - `kind` (TEXT) - 'topup', 'charge', 'refund', 'hold', 'release', 'adjust'
   - `amount_rub` (NUMERIC(12,2))
   - `status` (TEXT) - 'pending', 'done', 'failed', 'cancelled'
   - `ref` (TEXT) - Idempotency key (UNIQUE)
   - `meta` (JSONB) - Additional data
   - `created_at` (TIMESTAMP)

4. **jobs** (`app/database/schema.py:105-124`)
   - `id` (BIGSERIAL PRIMARY KEY)
   - `user_id` (BIGINT) - FK to users
   - `model_id` (TEXT) - KIE model ID
   - `category` (TEXT) - 'image', 'video', 'audio', etc.
   - `input_json` (JSONB) - Generation parameters
   - `price_rub` (NUMERIC(12,2))
   - `status` (TEXT) - 'draft', 'await_confirm', 'queued', 'running', 'done', 'failed', 'canceled'
   - `kie_task_id` (TEXT) - KIE API task ID
   - `kie_status` (TEXT) - KIE API status
   - `result_json` (JSONB) - KIE API response
   - `error_text` (TEXT) - Error message if failed
   - `idempotency_key` (TEXT UNIQUE) - Prevents duplicate jobs
   - `created_at`, `updated_at`, `finished_at` (TIMESTAMP)

5. **ui_state** (`app/database/schema.py:132-138`)
   - `user_id` (BIGINT PRIMARY KEY) - FK to users
   - `state` (TEXT) - Current FSM state
   - `data` (JSONB) - FSM data
   - `updated_at` (TIMESTAMP)
   - `expires_at` (TIMESTAMP) - Optional expiration

6. **free_models** (`app/database/schema.py:56-64`)
   - `model_id` (TEXT PRIMARY KEY)
   - `enabled` (BOOLEAN) - Whether free tier is enabled
   - `daily_limit` (INT) - Max free uses per day (default 5)
   - `hourly_limit` (INT) - Max free uses per hour (default 2)
   - `meta` (JSONB) - Additional config
   - `created_at`, `updated_at` (TIMESTAMP)

7. **free_usage** (`app/database/schema.py:69-75`)
   - `id` (BIGSERIAL PRIMARY KEY)
   - `user_id` (BIGINT) - FK to users
   - `model_id` (TEXT)
   - `job_id` (TEXT) - FK to jobs.id
   - `created_at` (TIMESTAMP)

8. **admin_actions** (`app/database/schema.py:81-95`)
   - `id` (BIGSERIAL PRIMARY KEY)
   - `admin_id` (BIGINT) - FK to users
   - `action_type` (TEXT) - 'model_enable', 'model_disable', 'user_topup', etc.
   - `target_type` (TEXT) - 'model', 'user', 'config', 'system'
   - `target_id` (TEXT) - Target identifier
   - `old_value`, `new_value` (JSONB) - Change tracking
   - `meta` (JSONB) - Additional data
   - `created_at` (TIMESTAMP)

9. **singleton_heartbeat** (`app/database/schema.py:143-147`)
   - `lock_id` (INTEGER PRIMARY KEY)
   - `instance_name` (TEXT) - Instance identifier
   - `last_heartbeat` (TIMESTAMP) - Last heartbeat time

### Migrations

**Location**: `app/database/schema.py:SCHEMA_SQL`  
**Strategy**: Idempotent (`CREATE TABLE IF NOT EXISTS`)  
**Execution**: On startup, if `DATABASE_URL` is set

---

## E. External Integrations

### KIE API

**Base URL**: `https://api.kie.ai` (configurable via `KIE_API_URL` env var)  
**Authentication**: `X-API-Key` header (from `KIE_API_KEY` env var)

### Endpoints

1. **Create Task**: `POST /api/v1/jobs/createTask`
   - Request body: `{"model": "...", "input": {...}, "callbackUrl": "..."}`
   - Response: `{"taskId": "...", "status": "queued"}`

2. **Get Task Info**: `GET /api/v1/jobs/recordInfo?taskId=...`
   - Response: `{"status": "done" | "running" | "failed", "result": {...}}`

### Callback Strategy

**Primary**: Webhook callback (`callbackUrl` in createTask request)  
**Fallback**: Polling (if callback fails or not configured)

**Callback URL**: `https://<webhook_base_url>/callbacks/kie`  
**Callback Token**: `X-KIE-Callback-Token` header (from `KIE_CALLBACK_TOKEN` env var)

### Timeout/Retry/Backoff Policy

**Request Timeout**: 30 seconds  
**Retry Count**: 3 attempts  
**Backoff**: Exponential (base 0.5s, max 5s)

---

## F. UI/UX Contract

### Main Menu Buttons

**Entry Point**: `/start` command  
**Buttons** (from `bot/handlers/flow.py`):

1. **🎨 Картинки и дизайн** (`cat:image`)
   - Category: `image`
   - Models: text-to-image, image-to-image, upscale, etc.

2. **🎬 Видео** (`cat:video`)
   - Category: `video`
   - Models: text-to-video, image-to-video, video-to-video, etc.

3. **🎵 Аудио** (`cat:audio`)
   - Category: `audio`
   - Models: text-to-speech, speech-to-text, audio-generation, etc.

4. **✨ Улучшение качества** (`cat:enhance`)
   - Category: `enhance`
   - Models: upscale, background-removal, watermark-removal, etc.

5. **🧑‍🎤 Аватары** (`cat:avatar`)
   - Category: `avatar`
   - Models: avatar generation, face swap, etc.

6. **🎵 Музыка** (`cat:music`)
   - Category: `music`
   - Models: music generation, sound effects, etc.

7. **⭐ Другое** (`cat:other`)
   - Category: `other`
   - Models: OCR, lip-sync, general, etc.

**Additional Buttons**:
- **💰 Баланс** (`balance`) - Show balance, top-up options
- **📜 История** (`history`) - Show generation history
- **🆘 Помощь** (`help`) - Show help message
- **🔍 Поиск модели** (`search`) - Search models by name
- **⭐ Лучшие модели** (`best_models`) - Show top models by quality/price

### Forbidden Phrases

**NEVER show**: "Старт с 200₽" or any specific amount in welcome message  
**Reason**: Amounts may change, creates false expectations

### Intended Flows

1. **Image Generation**:
   - `/start` → `cat:image` → select model → enter prompt → confirm → generate → result

2. **Video Generation**:
   - `/start` → `cat:video` → select model → enter prompt + optional image → confirm → generate → result

3. **Balance Top-Up**:
   - `/start` → `balance` → `topup` → enter amount → payment instructions

4. **History**:
   - `/start` → `history` → show last N generations → click to view details

---

## G. Config Contract

### Required Environment Variables

1. **TELEGRAM_BOT_TOKEN** (required)
   - Format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
   - Source: @BotFather on Telegram
   - Usage: Bot API authentication

2. **DATABASE_URL** (required for production)
   - Format: `postgresql://user:password@host:port/database`
   - Source: Render PostgreSQL dashboard
   - Usage: Database connection (users, wallets, jobs, etc.)

3. **KIE_API_KEY** (required for generation)
   - Format: `kie_abc123def456ghi789jkl`
   - Source: https://kie.ai/settings/api-keys
   - Usage: KIE API authentication

4. **ADMIN_ID** (optional, but recommended)
   - Format: `123456789` (Telegram user ID)
   - Source: @userinfobot on Telegram
   - Usage: Admin access (model enable/disable, user top-up, etc.)

### Optional Environment Variables

5. **BOT_MODE** (default: `webhook`)
   - Values: `webhook`, `polling`
   - Usage: Runtime mode selection

6. **PORT** (default: `0` = no healthcheck)
   - Format: `8000` (integer)
   - Usage: HTTP server port for healthcheck/webhook

7. **WEBHOOK_BASE_URL** (required if BOT_MODE=webhook)
   - Format: `https://yourapp.onrender.com`
   - Usage: Webhook URL base

8. **WEBHOOK_SECRET_PATH** (optional, auto-derived from token if not set)
   - Format: `secret_path_123`
   - Usage: Webhook secret path (part of URL)

9. **WEBHOOK_SECRET_TOKEN** (optional, but recommended)
   - Format: `secret_token_xyz`
   - Usage: Webhook secret token (X-Telegram-Bot-Api-Secret-Token header)

10. **KIE_CALLBACK_PATH** (default: `callbacks/kie`)
    - Format: `callbacks/kie`
    - Usage: KIE callback URL path

11. **KIE_CALLBACK_TOKEN** (optional, but recommended)
    - Format: `callback_token_secret`
    - Usage: KIE callback token (X-KIE-Callback-Token header)

12. **USD_RUB_RATE** (default: fixed constant or env var)
    - Format: `95.5` (float)
    - Usage: USD to RUB exchange rate for pricing

13. **LOCK_KEY1**, **LOCK_KEY2** (default: `214748364`, `2`)
    - Format: Signed int32
    - Usage: PostgreSQL advisory lock keys

14. **LOCK_MODE** (default: `wait_then_passive`)
    - Values: `wait_then_passive`, `wait_then_force`
    - Usage: Lock acquisition behavior

15. **LOCK_WAIT_SECONDS** (default: `60`)
    - Format: Integer
    - Usage: Max wait time for lock acquisition

16. **SINGLE_MODEL_ONLY** (default: `0`)
    - Values: `1` (true), `0` (false)
    - Usage: Enable only z-image model

17. **DRY_RUN** (default: `0`)
    - Values: `1` (true), `0` (false)
    - Usage: Skip actual KIE API calls (testing)

18. **TEST_MODE** (default: `0`)
    - Values: `1` (true), `0` (false)
    - Usage: Enable test mode (skip payments, etc.)

19. **LOG_LEVEL** (default: `INFO`)
    - Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`
    - Usage: Logging verbosity

20. **PAYMENT_PHONE**, **PAYMENT_BANK**, **PAYMENT_CARD_HOLDER** (optional)
    - Format: Strings
    - Usage: Payment instructions for top-up

21. **SUPPORT_TELEGRAM**, **SUPPORT_TEXT** (optional)
    - Format: Strings
    - Usage: Support contact info

---

## H. Smoke Checks

### Exact Endpoints

1. **Health Check**: `GET /health`
   - Expected: `200 OK`
   - Response: `{"ok": true, "mode": "active" | "passive", "lock_acquired": true | false, "ts": "..."}`
   - Command: `curl https://yourapp.onrender.com/health`

2. **Webhook Fast-Ack**: `POST /webhook/<secret_path>`
   - Headers: `X-Telegram-Bot-Api-Secret-Token: <secret_token>`
   - Body: `{"update_id": 123, "message": {...}}`
   - Expected: `200 OK` in <200ms
   - Command: `curl -X POST https://yourapp.onrender.com/webhook/<secret_path> -H "X-Telegram-Bot-Api-Secret-Token: <token>" -d '{"update_id": 123}'`

3. **KIE Callback**: `POST /callbacks/kie`
   - Headers: `X-KIE-Callback-Token: <callback_token>`
   - Body: `{"taskId": "...", "status": "done", "result": {...}}`
   - Expected: `200 OK`
   - Command: `curl -X POST https://yourapp.onrender.com/callbacks/kie -H "X-KIE-Callback-Token: <token>" -d '{"taskId": "test", "status": "done"}'`

### Exact Commands

**Local Smoke Test**:
```bash
python scripts/smoke_webhook.py
```

**Production Smoke Test**:
```bash
python scripts/smoke.py --url https://yourapp.onrender.com --env production
```

### Expected Outputs

**Health Check**:
```json
{
  "ok": true,
  "mode": "active",
  "lock_acquired": true,
  "ts": "2026-01-14T07:00:00Z"
}
```

**Webhook**:
```
200 OK
ok
```

**Smoke Test**:
```
✅ PASS: Import main_render
✅ PASS: Create dp/bot
✅ PASS: Simulate callback event
✅ PASS: Fallback handler
✅ PASS: Telemetry signatures
✅ ALL TESTS PASSED (5/5)
```

---

## I. Known Failure Modes

### 1. PASSIVE_REJECT

**Symptom**: Log shows `⏸️ PASSIVE_REJECT callback_query data=cat:image`  
**Meaning**: Instance is in PASSIVE mode (lock not acquired)  
**Acceptable**: During Render deploy overlap (old instance ACTIVE, new instance PASSIVE)  
**Unacceptable**: PASSIVE mode lasting >5 minutes (indicates stuck lock)

**Recovery**:
- Check `/health` endpoint: `"mode": "passive"`, `"lock_acquired": false`
- Check Render logs for lock acquisition attempts
- If stuck: restart Render service (forces lock release)

### 2. Render Deploy Overlap

**Symptom**: Two instances running simultaneously (old + new)  
**Behavior**: Old instance ACTIVE (has lock), new instance PASSIVE (waiting for lock)  
**Duration**: Usually 10-30 seconds (until old instance shuts down)

**Expected Logs**:
```
[LOCK] ⏸️ PASSIVE MODE: Webhook will return 200 but no processing
[LOCK] Background retry task will attempt to acquire lock periodically
```

**Recovery**: Wait for old instance to shut down (automatic)

### 3. Webhook Secret Mismatch

**Symptom**: Telegram returns `404 Not Found` or `403 Forbidden`  
**Cause**: `WEBHOOK_SECRET_PATH` or `WEBHOOK_SECRET_TOKEN` mismatch

**Recovery**:
- Check `WEBHOOK_SECRET_PATH` matches Telegram webhook URL
- Check `WEBHOOK_SECRET_TOKEN` matches Telegram webhook secret token
- Re-set webhook: `curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook -d "url=https://yourapp.onrender.com/webhook/<secret_path>&secret_token=<secret_token>"`

### 4. DB Pool Limits / Locks

**Symptom**: `asyncpg.exceptions.TooManyConnections` or `PostgreSQL advisory lock timeout`  
**Cause**: Too many concurrent connections or stuck lock

**Recovery**:
- Check connection pool size (max=10)
- Check for stuck locks: `SELECT * FROM pg_locks WHERE locktype = 'advisory'`
- Restart Render service (forces connection cleanup)

### 5. KIE API Timeout

**Symptom**: `TimeoutError` or `502 Bad Gateway` from KIE API  
**Cause**: KIE API slow or unavailable

**Recovery**:
- Check KIE API status: `curl https://api.kie.ai/health`
- Retry logic handles this automatically (exponential backoff)
- If persistent: check `KIE_API_KEY` validity

---

## J. Versioned Decisions (ADR-lite)

### ADR-001: Fast-Ack Webhook Architecture

**Decision**: Webhook handler returns 200 OK immediately, processing happens in background workers  
**Reason**: Telegram requires <5s response, prevents timeout retries  
**Trade-off**: Slight delay in user response (acceptable, <1s typical)

### ADR-002: PostgreSQL Advisory Lock for Singleton

**Decision**: Use PostgreSQL advisory lock (session-level) instead of file lock  
**Reason**: Works across multiple Render instances, no file system dependency  
**Trade-off**: Requires DATABASE_URL (acceptable, already required)

### ADR-003: PASSIVE Mode During Deploy Overlap

**Decision**: New instance starts in PASSIVE mode if lock not acquired  
**Reason**: Prevents duplicate processing during rolling deploy  
**Trade-off**: Brief period where new instance doesn't process (acceptable, <30s typical)

### ADR-004: Canonical Model Registry (SSOT)

**Decision**: `models/KIE_SOURCE_OF_TRUTH.json` is the only source of truth for models/pricing  
**Reason**: Prevents drift, ensures consistency  
**Trade-off**: Manual updates require verification (acceptable, infrequent)

### ADR-005: Pricing Formula (2x Markup)

**Decision**: `RUB = KIE_USD * 2.0 * FX_RATE`  
**Reason**: Simple, predictable, covers costs + margin  
**Trade-off**: Fixed markup (acceptable, can adjust FX_RATE if needed)

---

**End of TRT_SYSTEM.md**

