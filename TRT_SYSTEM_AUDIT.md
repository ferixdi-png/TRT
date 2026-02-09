# TRT System Audit Report
## Date: 2026-02-09

---

## 0. System Map

### Entrypoints
| Entry | File | Purpose |
|-------|------|---------|
| **Bot** | `entrypoints/run_bot.py` | Main bot entry (webhook/polling) |
| **Main Render** | `main_render.py` | Render.com deployment entry |
| **Webapp** | `webapp/aiohttp_handlers.py` | Mini App HTTP handlers |

### Core Modules
| Module | Path | Purpose |
|--------|------|---------|
| **Bot Logic** | `bot_kie.py` | Main bot handlers (1.4MB!) |
| **Storage** | `app/storage/` | PostgreSQL, JSON, GitHub storage |
| **Pricing** | `app/pricing/` | Price resolver, SSOT, free policy |
| **Generations** | `app/generations/` | Universal engine, job lifecycle |
| **KIE Contract** | `app/kie_contract/` | Payload builder, normalizer |
| **KIE Catalog** | `app/kie_catalog/` | Models pricing, specs |

### ENV/Config
| File | Purpose |
|------|---------|
| `.env` | Local environment |
| `app/config.py` | App configuration |
| `app/config_env.py` | ENV loading |

### Billing/Balance
| File | Function |
|------|----------|
| `app/storage/postgres_storage.py` | `charge_balance_once`, `subtract_user_balance`, `consume_free_generation_once` |
| `webapp/aiohttp_handlers.py` | Balance check + charge after generation |
| `bot_kie.py` | `_charge_balance_once`, balance deduction |

---

## TOP-10 Risks (P0/P1)

### P0 - Security/Money/Crashes

| # | Risk | File | Status |
|---|------|------|--------|
| **1** | ~~Double charge on retry/double-click~~ | `app/storage/postgres_storage.py` | ✅ `charge_balance_once` uses task_id deduplication |
| **2** | ~~Webapp missing balance charge~~ | `webapp/aiohttp_handlers.py:620-680` | ✅ Fixed today |
| **3** | ~~Path traversal in uploads~~ | `webapp/aiohttp_handlers.py:410-430` | ✅ Fixed today |
| **4** | Race condition on balance | `app/storage/postgres_storage.py` | ✅ Uses `FOR UPDATE` locks |
| **5** | Missing refund on provider failure | `app/generations/universal_engine.py` | ⚠️ VERIFY - charge happens AFTER success |

### P1 - UX Dead-ends/Silence

| # | Risk | File | Status |
|---|------|------|--------|
| **6** | Unclear input requirements | `app/models/input_schema.py` | ✅ UX schema with labels/hints |
| **7** | ~~prompt required for i2v models~~ | `webapp/aiohttp_handlers.py:459-465` | ✅ Fixed today |
| **8** | Bot silence during long jobs | `bot_kie.py` | ⚠️ VERIFY progress updates |
| **9** | Mismatched labels bot/webapp | `helpers.py`, `webapp/` | ⚠️ AUDIT needed |
| **10** | Missing WEBAPP_URL behavior | `helpers.py:104-137` | ✅ Graceful - button hidden if not set |

---

## Fixes Applied Today (2026-02-09)

1. **Balance charging in webapp** - `charge_balance_once` + `consume_free_generation_once`
2. **Path traversal security** - regex + resolve() validation
3. **int() exception handling** - try/except for user_id parsing
4. **prompt optional for i2v** - i2v models don't require prompt
5. **File size limit** - MAX_UPLOAD_SIZE = 20MB
6. **is_free in retry job** - proper tracking
7. **import re cleanup** - moved to file top
8. **asyncio task naming** - for debugging
9. **requires_video/audio in model_info** - full media requirements

---

## Next Steps

1. [ ] Verify bot progress updates during long jobs
2. [ ] Audit label consistency bot ↔ webapp
3. [ ] Verify refund behavior on provider failure
4. [ ] Create UX_MAP.md
5. [ ] Create JOB_PIPELINE.md
6. [ ] Create ENV_CHECKLIST.md
7. [ ] Run smoke tests

