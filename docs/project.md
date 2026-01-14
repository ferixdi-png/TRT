# Project Overview

**Name**: TRT (Telegram AI Generation Bot)  
**Status**: Production (Render deployment)  
**Stage**: Post-emergency stabilization → Million-ready preparation  
**Last Updated**: 2026-01-13

---

## What We Do

Multi-modal AI generation Telegram bot with 70+ models via KIE.ai API.

**Core Value Proposition**:
- **User**: One-stop AI shop (text→image, image→video, upscale, etc.) in Telegram
- **Business**: Credit-based monetization, plug-in model architecture, scalable
- **Technical**: Webhook-driven, idempotent, production-hardened

---

## Key User Scenarios (P0)

### 1. New User Onboarding
1. `/start` → welcome message + free credits (if configured)
2. User selects model category (e.g., "Image Generation")
3. User selects specific model (e.g., "z-image")
4. User sends prompt → bot generates → delivers result
5. Balance deducted atomically (hold → charge)

**Success Criteria**:
- <5s from prompt to "generating..." message
- Result delivered within model SLA (30s-5min depending on model)
- Zero double-charges
- Clear error messages if balance insufficient

### 2. Model Usage (z-image baseline)
1. User types `/start` → main menu
2. Selects "Текст → Картинка"
3. Selects "z-image" (FREE tier model)
4. Sends prompt: "космический корабль в стиле киберпанк"
5. Bot:
   - Validates input
   - Checks balance (FREE = 0 credits)
   - Calls KIE.ai API
   - Waits for callback
   - Delivers image

**Success Criteria**:
- z-image works 99% of time (baseline reliability)
- Other models fail gracefully with actionable errors
- No webhook 409 conflicts
- No payment race conditions

### 3. Balance Top-up (future)
1. User clicks "Пополнить баланс"
2. Selects amount (100₽, 500₽, 1000₽)
3. Payment link generated
4. User pays via YooKassa/similar
5. Webhook confirms payment → balance updated
6. User notified

**Success Criteria** (not yet implemented):
- Idempotent payment processing
- Clear audit trail in `ledger` table
- No lost payments

---

## "Million-Ready" Definition

Project is **ready to sell for 1M** when:

### Technical (Must-have)
- ✅ Production stable: no restart loops, clean logs
- ✅ Single Source of Truth enforced (migrations, models, ENV)
- ✅ Webhook fast-ack + idempotent update processing
- ✅ Billing atomicity (hold/charge/refund) proven
- 🚧 Plug-in model system (90% done, needs validation automation)
- 🚧 Zero manual intervention for 1 week straight

### Business (Must-have)
- ❌ Payment integration live (YooKassa/similar)
- ❌ Revenue > 10K₽/month (real users paying)
- ❌ 100+ active users
- 🚧 Cost per generation < 80% of price (profit margin)

### Product (Should-have)
- ✅ 70+ models available
- 🚧 Model discovery/search UX
- 🚧 Result preview before payment (for expensive models)
- ❌ Referral system (growth driver)

### Governance (Must-have)
- ✅ Documented architecture (SSOT, deployment)
- 🚧 Automated smoke tests catch 90% of regressions
- 🚧 Rollback procedure tested in production
- ❌ On-call playbook (what to do when X breaks)

**Legend**:
- ✅ Done
- 🚧 In progress / partial
- ❌ Not started

---

## Current State (2026-01-13)

### What Works
- **Deployment**: Render auto-deploy from `main` branch
- **Lock**: Singleton pattern prevents 409 conflicts
- **Migrations**: Auto-applied, idempotent
- **Webhook**: Fast-ack, processed_updates dedup
- **z-image**: Baseline model functional
- **Health**: `/health` endpoint with migrations status

### Known Issues (Post-Hotfix)
- ✅ **FIXED**: Heartbeat type signature → migration 011 deployed
- ✅ **FIXED**: Lock takeover loops → threshold increased to 120s
- 🚧 **Monitoring**: No alerting on lock takeover frequency
- 🚧 **Testing**: Smoke test doesn't verify lock behavior
- ❌ **Payments**: No real payment integration yet
- ❌ **Model Validation**: Manual testing, not automated

### Tech Debt
1. **15+ smoke scripts** → consolidate into `smoke_unified.py` variants
2. **No schema version table** → can't track which migrations applied
3. **Lock logging spam** → reduced but could be better
4. **No graceful shutdown** → process termination abrupt
5. **Deprecated models JSON** → still in repo (moved to _deprecated/)

---

## Stack

### Runtime
- **Language**: Python 3.11
- **Framework**: aiogram 3.x (Telegram bot)
- **Web**: aiohttp (webhook + health endpoints)
- **DB**: PostgreSQL (asyncpg)
- **Platform**: Render (Web Service)

### External APIs
- **Telegram**: Bot API (webhook mode)
- **KIE.ai**: 70+ AI models (text→image, image→video, etc.)
- **Payments**: (planned) YooKassa/similar

### Key Libraries
- `asyncpg` - async PostgreSQL
- `aiogram` - Telegram bot framework
- `aiohttp` - HTTP server
- `psycopg2` - sync PostgreSQL (advisory locks)
- `requests` - KIE.ai API calls

---

## Data Flow (High-Level)

```
User (Telegram)
  ↓ message
Telegram Servers
  ↓ webhook POST
/webhook/{secret} (aiohttp)
  ↓ fast-ack (200 OK)
Update Queue (asyncio.Queue)
  ↓ worker dequeues
aiogram Dispatcher
  ↓ handler routing
Business Logic
  ├─ Balance Check (DB transaction)
  ├─ KIE.ai API Call (async)
  └─ Result Delivery
      ↓ callback webhook
/kie_callback/{token}
  ↓ updates job status
Deliver to User
```

### Critical Paths
1. **Webhook → Queue** (<10ms, must be fast)
2. **Queue → Handler** (async workers, 1-5 concurrent)
3. **Balance Operations** (atomic transactions, idempotent)
4. **KIE Callback** (idempotent processing, retries)

---

## Modules (Boundaries)

### `/app/handlers/` - User Interaction
- **Role**: aiogram message/callback handlers
- **Contract**: No direct DB access (uses services)
- **Inputs**: Telegram `Message`, `CallbackQuery`
- **Outputs**: Bot responses, FSM state transitions

### `/app/services/` - Business Logic
- **Role**: Orchestrate DB + KIE + billing
- **Contract**: Async, idempotent
- **Examples**:
  - `user_service.py` - user management
  - `generation_service_v2.py` - generation orchestration
  - `job_service_v2.py` - job lifecycle + billing

### `/app/database/` - Data Layer
- **Role**: PostgreSQL operations (asyncpg)
- **Contract**: Transactions, idempotency, connection pooling
- **Files**:
  - `services.py` - WalletService, UserService, etc.
  - `schema.py` - table definitions

### `/app/kie/` - External API
- **Role**: KIE.ai integration
- **Contract**: Single payload builder, unified error handling
- **Files**:
  - `builder.py` - load SSOT, build payloads
  - `router.py` - route to correct executor
  - `generator.py` - actual API calls + retries

### `/app/locking/` - Singleton Control
- **Role**: Advisory lock, active/passive state
- **Contract**: Only ONE instance processes updates
- **Files**:
  - `single_instance.py` - lock acquisition
  - `controller.py` - state machine
  - `active_state.py` - shared state

### `/app/storage/` - Persistence Abstraction
- **Role**: PostgreSQL vs JSON storage (legacy)
- **Contract**: Uniform interface for both
- **Status**: PostgreSQL-only in production

---

## Patterns & Invariants

### Idempotency
- **Update processing**: `processed_updates` table (dedup by `update_id`)
- **Billing**: `ledger.ref` column (unique per transaction)
- **KIE callbacks**: job status checked before processing

### Concurrency Control
- **Lock**: PostgreSQL advisory lock (singleton)
- **Queue**: asyncio.Queue with backpressure
- **DB**: connection pooling, transaction isolation

### Error Handling
- **Telegram**: User-friendly messages, no stack traces
- **KIE API**: Retry with exponential backoff, timeout after 5min
- **Billing**: Rollback on failure, audit trail

### Billing Model
1. **Hold** (reserve funds) → `ledger.kind='hold'`
2. **Charge** (on success) → `ledger.kind='charge'`
3. **Refund** (on failure) → `ledger.kind='refund'`

**Invariant**: `balance + hold = total_funds`

---

## Monitoring & Observability

### Logs
- **Format**: timestamp, level, correlation_id, message
- **Location**: stdout (Render captures)
- **Levels**: INFO (default), DEBUG (troubleshooting)

**Key log patterns**:
```
[LOCK] ✅ ACTIVE MODE - lock acquired
[MIGRATIONS] ✅ All migrations applied
[WEBHOOK_ACTIVE] ✅ Webhook ensured
[BALANCE] user=123 charged=10.50 job=abc123
```

### Health Endpoint
- **URL**: `GET /health`
- **Purpose**: Render health check + monitoring
- **Metrics**: uptime, migrations, lock state, takeover events

### Metrics (planned)
- Request rate (updates/sec)
- Generation success rate (per model)
- Balance operations (topups, charges, refunds)
- Lock takeover frequency (should be 0)

---

## Git Workflow

### Branches
- `main` - production (auto-deploy to Render)
- Feature branches - not used (direct commits to main for now)

### Commits
- Conventional commits preferred: `fix:`, `feat:`, `docs:`, `hotfix:`
- Atomic commits (one logical change)
- Include context in message body for complex changes

### Deploy
- Push to `main` → Render auto-deploys (~3-5min)
- No manual approval required
- Rollback via Render dashboard if needed

---

## Roadmap (Next 2-4 Weeks)

### Week 1 (Current)
- ✅ Emergency hotfix: heartbeat type signature
- 🚧 Consolidate smoke tests
- 🚧 Add schema version tracking
- ❌ Document all patterns in docs/patterns.md

### Week 2
- 🎯 Payment integration (YooKassa)
- 🎯 Model validation automation
- 🎯 Lock metrics in /health
- 🎯 Graceful shutdown on lock loss

### Week 3
- 🎯 Referral system MVP
- 🎯 Admin panel (web UI for analytics)
- 🎯 Cost optimization (cheaper models routing)

### Week 4
- 🎯 Load testing (1000 concurrent users)
- 🎯 Production monitoring (alerting)
- 🎯 Documentation freeze (all patterns documented)

**Goal**: 100+ paying users, 1-week zero-intervention uptime

---

## Contact & Support

- **Owner**: ferixdi-png
- **Repo**: github.com/ferixdi-png/TRT
- **Deployment**: https://five656.onrender.com
- **Telegram**: Bot running in production (token env-only)

---

## References

- [Architecture](architecture/SSOT.md)
- [Deployment](deployment.md)
- [Database Schema](../app/database/schema.py)
- [ENV Contract](../app/utils/startup_validation.py)
