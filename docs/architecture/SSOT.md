# Single Source of Truth (SSOT) Architecture

**Last Updated**: 2026-01-13  
**Status**: ✅ Enforced

## Overview

This document defines the canonical sources of truth for all runtime data. Any code reading configuration, models, pricing, or schema MUST use these sources.

## 1. Migrations (Database Schema)

**SSOT Location**: `/migrations/*.sql`

**Rules**:
- ALL migrations live ONLY in `/migrations/` directory
- Numbered sequentially: `001_*.sql`, `002_*.sql`, etc.
- Applied automatically via `app/storage/migrations.py::apply_migrations_safe()`
- Idempotent (uses `CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, etc.)

**What Was Fixed**:
- ❌ Removed duplicate `/app/storage/migrations/` directory
- ❌ Removed orphan `005_consolidate_schema.sql.OLD`
- ✅ Consolidated to single location

**Migration List** (as of 2026-01-13):
```
001_initial_schema.sql
002_balance_reserves.sql
003_users_username.sql
004_orphan_callbacks.sql
005_add_columns.sql
006_create_tables.sql
007_lock_heartbeat.sql
008_processed_updates.sql
009_add_delivering_at.sql
010_delivery_lock_platform_wide.sql
```

## 2. Model Catalog (KIE Models, Pricing, Schemas)

**SSOT Location**: `/models/KIE_SOURCE_OF_TRUTH.json`

**Rules**:
- ALL model definitions, pricing, input schemas come from this ONE file
- NO other JSON files in `/models/` are used at runtime
- Loaded via `app/kie/builder.py::load_source_of_truth()`
- Cached with `@lru_cache` for performance

**What Was Fixed**:
- ❌ Moved 18+ duplicate JSON files to `/models/_deprecated/`
- ✅ Updated `app/kie/builder.py` to enforce canonical path
- ✅ Added deprecation notice in `/models/_deprecated/README.md`

**Deprecated Files** (moved, DO NOT USE):
- `kie_parsed_models.json`
- `kie_scraped_models.json`
- `kie_api_models.json`
- `kie_registry.generated.json`
- ... (all others)

## 3. Environment Variables

**SSOT Location**: `app/utils/startup_validation.py::REQUIRED_ENV_KEYS`

**Rules**:
- ALL required ENV keys listed in `REQUIRED_ENV_KEYS` constant
- Validation MUST run before any DB/network operations
- Called at start of `main_render.py::main()`

**Required Keys** (see `startup_validation.py` for full list):
```python
REQUIRED_ENV_KEYS = [
    'ADMIN_ID',
    'BOT_MODE',
    'DATABASE_URL',
    'DB_MAXCONN',
    'KIE_API_KEY',
    'PAYMENT_BANK',
    'TELEGRAM_BOT_TOKEN',
    'WEBHOOK_BASE_URL',
    # ... etc
]
```

**What Was Fixed**:
- ✅ Added `startup_validation()` call at top of `main()` before any other operations
- ✅ Blocks startup on missing required keys

## 4. Runtime State

**SSOT Location**: `app/utils/runtime_state.py`

**Rules**:
- In-memory state tracking (bot_mode, start_time, lock status, etc.)
- Accessed via `runtime_state` singleton
- NOT persisted (ephemeral per-instance)

## 5. Health Check

**Endpoint**: `GET /health`

**Rules**:
- Returns JSON with migrations status, lock state, uptime
- Uses `app/storage/migrations.py::check_migrations_status()`
- Render/UptimeRobot polls this for liveness

**What Was Fixed**:
- ✅ Added `migrations_applied` and `migrations_count` to health response
- ✅ Added `check_migrations_status()` function

## Anti-Patterns (DO NOT DO)

❌ **Don't create parallel migration directories**  
❌ **Don't read from deprecated JSON files in `/models/_deprecated/`**  
❌ **Don't hardcode ENV checks outside `startup_validation.py`**  
❌ **Don't use `asyncio.run()` or `loop.run_until_complete()` in async runtime**  
❌ **Don't create per-feature "truth" files without updating this doc**

## Verification

Run unified smoke test to verify SSOT integrity:

```bash
python3 scripts/smoke_unified.py
```

Tests:
- ENV validation
- DB migrations applied
- KIE_SOURCE_OF_TRUTH loads correctly
- z-image baseline model present
- Webhook queue initialized
- Billing idempotency

## References

- [ENV Documentation](./env.md)
- [Database Schema](../app/database/schema.py)
- [Migration Runner](../app/storage/migrations.py)
- [Model Builder](../app/kie/builder.py)
