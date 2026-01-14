# Architecture

**Blessed Path**: `main_render.py` → единственный production entrypoint

## High-Level Flow

```
User (Telegram) → Telegram API → Webhook POST → main_render.py
  → UpdateQueueManager (fast-ack 200 OK) → asyncio.Queue
  → Worker tasks → Dispatcher.feed_update() → Handlers
  → DatabaseService / KIE.ai API → Response to user
```

## Directory Structure (Blessed Components Only)

```
/workspaces/TRT/
├── main_render.py          ← ENTRYPOINT (aiohttp app)
├── product/
│   └── truth.yaml          ← SINGLE SOURCE OF TRUTH
├── kb/                     ← Knowledge base (for AI agent context)
│   ├── project.md
│   ├── architecture.md     ← THIS FILE
│   ├── patterns.md
│   ├── features.md
│   ├── database.md
│   ├── deployment.md
│   └── monitoring.md
├── scripts/
│   ├── verify.py           ← Architecture gate (CI)
│   └── smoke.py            ← Smoke tests S0-S8 (CI)
├── app/                    ← Application code
│   ├── locking/            ← Singleton lock (PostgreSQL advisory)
│   │   ├── controller.py
│   │   └── single_instance.py
│   ├── utils/
│   │   ├── update_queue.py ← Fast-ack queue manager
│   │   └── webhook.py      ← Webhook setup/teardown
│   ├── database/
│   │   └── services.py     ← DatabaseService (connection pool)
│   └── handlers/           ← aiogram handlers (message/callback routers)
├── render_singleton_lock.py ← PostgreSQL advisory lock primitives
├── migrations/             ← SQL schema migrations
├── tests/                  ← Unit tests (pytest)
└── quarantine/             ← Legacy code (не участвует в runtime)
```

## Core Components

### 1. Entrypoint: main_render.py
- aiohttp web app (port from $PORT env)
- Routes: `/health`, `/webhook/{secret}`, `/kie-callback`
- Lock controller: acquire PostgreSQL advisory lock or go PASSIVE
- Lifecycle: setup webhook → init database → run dispatcher

### 2. Lock Controller (app/locking/controller.py)
- **ACTIVE mode**: Holds advisory lock, processes all updates
- **PASSIVE mode**: No lock, fast-ack only whitelisted operations
- Lock mechanism: PostgreSQL `pg_try_advisory_lock(classid, objid)` (signed int32)
- Heartbeat: Update lock_heartbeat table every 30s
- Takeover: If lock holder idle > 5 minutes, force takeover

### 3. UpdateQueueManager (app/utils/update_queue.py)
- Fast-ack pattern: HTTP 200 OK within 500ms
- asyncio.Queue (max size 100)
- 4 worker tasks consume from queue → Dispatcher.feed_update()
- PASSIVE logic: Whitelist check → instant reject or allow
- Metrics: total_received, total_processed, queue_depth, drop_rate

### 4. DatabaseService (app/database/services.py)
- Connection pool (psycopg2.pool.ThreadedConnectionPool)
- Manages pool lifecycle (init/close)
- Transactions: context manager for BEGIN/COMMIT/ROLLBACK
- Used by handlers (no direct psycopg2 imports in handlers)

### 5. Handlers (app/handlers/)
- aiogram routers (message, callback_query)
- Декларативный routing через decorators
- Никогда не блокируют (always async)
- Используют DatabaseService для persistence

## Integration Points

### External Services
- **Telegram Bot API**: Webhook for updates, sendMessage/answerCallbackQuery for responses
- **KIE.ai API**: Image/video generation (https://api.kie.ai)
- **PostgreSQL**: Storage + advisory lock
- **Render**: Hosting platform (auto-deploy from GitHub main)

### Security Boundaries
- Webhook secret token (в URL path)
- KIE callback signature verification
- Admin IDs check (env ADMIN_IDS)
- No secrets in logs

## State Management

### Global State (Singletons)
- `runtime_state` (app/utils/runtime_state.py): uptime, bot_mode, lock status
- `active_state` (app/locking/active_state.py): ACTIVE/PASSIVE flag
- `UpdateQueueManager` instance: webhook queue
- `DatabaseService` instance: connection pool

### Persistent State (PostgreSQL)
- `user_balances`: balance, currency
- `transactions`: payment history
- `jobs`: generation requests (status, result_url)
- `lock_heartbeat`: lock holder heartbeat

## Failure Modes & Recovery

### Instance crashes
- Lock auto-released by PostgreSQL (session-level)
- New instance takes lock immediately

### Lock held by dead instance
- Heartbeat age > 5 minutes → takeover logic triggers
- Forceful lock acquisition (release + re-acquire)

### Queue overflow
- Drop oldest update when queue full
- Metric: drop_rate (должен быть < 1%)

### Database unavailable
- Connection timeout 10s → log error, enter PASSIVE mode
- Retry with exponential backoff

### KIE.ai API error
- Job marked as failed in database
- User notified with error message
- No retry loop (user re-submits manually)

## Design Decisions

### Why single entrypoint?
- Проще debugging (один call stack)
- Нет race conditions между конкурирующими entrypoints
- CI/CD проще (один build, один deploy)

### Why advisory lock instead of Redis/leader election?
- PostgreSQL уже есть (no extra dependency)
- Session-level lock = automatic cleanup on crash
- Atomic operations (pg_try_advisory_lock returns bool immediately)

### Why fast-ack pattern?
- Telegram webhook timeout ~30 seconds
- Длинные операции (генерация) могут занимать минуты
- 200 OK сразу → работа в фоне → callback_query.answer() позже

### Why PASSIVE mode instead of exit?
- Graceful degradation (меню/статус работают)
- Пользователь не видит "бот не отвечает"
- Полезно для rolling deploys (zero-downtime)

## Forbidden Patterns

❌ **Multiple entrypoints**: Только main_render.py  
❌ **Wildcard imports**: `from module import *`  
❌ **Direct psycopg2 in handlers**: Только через DatabaseService  
❌ **Blocking code in async**: `time.sleep()` → `asyncio.sleep()`  
❌ **Unsigned int в advisory lock**: Требуется signed int32  
❌ **Decimal в JSON response**: Конвертить в float явно
