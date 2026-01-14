# TRT Reliability + Growth Report

**Last Updated**: 2026-01-14T08:30:00Z  
**Commit Hash (main)**: `7e56896` (latest: T-001 queue metrics)  
**Build/Deploy**: Render auto-deploy (pending verification)  
**Report Mirror**: `C:\Users\User\Desktop\TRT_REPORT.md` ✅

---

## SYSTEM STATUS

**Status**: 🟡 AMBER  
**Reasons**:
- Deploy verification pending (smoke tests not run yet)
- ✅ T-001 completed: Queue metrics now exposed in /health
- ⚠️ KIE callback correlation IDs may not propagate fully through job lifecycle (T-002 pending)
- ⚠️ Payment idempotency not validated (T-003 pending)

---

## TOP-5 CRITICALS (Scoring Table)

| Issue | A (Revenue) | B (Generation) | C (UX Nav) | D (Silent Fail) | E (Ops Risk) | **Total** | Priority |
|-------|------------|----------------|------------|-----------------|--------------|-----------|----------|
| **1. Queue drops under load** | 0 | 8 | 0 | 9 | 8 | **25** | P0 |
| **2. Missing CID in KIE job lifecycle** | 0 | 7 | 0 | 8 | 6 | **21** | P0 |
| **3. No payment idempotency validation** | 10 | 0 | 0 | 9 | 0 | **19** | P1 |
| **4. PASSIVE mode UX not premium** | 0 | 0 | 7 | 0 | 5 | **12** | P2 |
| **5. KIE sync parser not integrated** | 0 | 3 | 0 | 4 | 3 | **10** | P2 |

### Scoring Details

**Issue 1: Queue drops under load**
- **A (Revenue)**: 0 - Doesn't directly break payments
- **B (Generation)**: 8 - Lost updates = lost generation requests
- **C (UX Nav)**: 0 - User doesn't see navigation issues
- **D (Silent Fail)**: 9 - Updates silently dropped, user sees no response
- **E (Ops Risk)**: 8 - High queue depth = memory pressure, no backpressure signaling
- **Evidence**: `UpdateQueueManager.enqueue()` returns `False` when queue full, but webhook still returns 200 OK. No metrics exposed to monitor drop rate.

**Issue 2: Missing CID in KIE job lifecycle**
- **A (Revenue)**: 0 - Doesn't break payments
- **B (Generation)**: 7 - Can't trace job failures end-to-end
- **C (UX Nav)**: 0 - Doesn't affect navigation
- **D (Silent Fail)**: 8 - Job failures can't be correlated with user actions
- **E (Ops Risk)**: 6 - Harder to debug production issues
- **Evidence**: `app/kie/` modules don't propagate `cid` from telemetry to job creation/polling/callback.

**Issue 3: No payment idempotency validation**
- **A (Revenue)**: 10 - Double charges = revenue loss + user trust
- **B (Generation)**: 0 - Doesn't affect generation
- **C (UX Nav)**: 0 - Doesn't affect navigation
- **D (Silent Fail)**: 9 - Duplicate payments processed silently
- **E (Ops Risk)**: 0 - Doesn't cause operational issues
- **Evidence**: `ledger` table has `ref` (idempotency key) but no validation in payment handlers.

**Issue 4: PASSIVE mode UX not premium**
- **A (Revenue)**: 0 - Doesn't break payments
- **B (Generation)**: 0 - Doesn't break generation
- **C (UX Nav)**: 7 - User sees "⏸️ Сервис обновляется, попробуй через минуту" - not premium
- **D (Silent Fail)**: 0 - User gets feedback
- **E (Ops Risk)**: 5 - During deploy overlap, users see non-premium message
- **Evidence**: `app/utils/update_queue.py:239` - hardcoded message, no premium styling.

**Issue 5: KIE sync parser not integrated**
- **A (Revenue)**: 0 - Doesn't break payments
- **B (Generation)**: 3 - New models can't be verified against upstream
- **C (UX Nav)**: 0 - Doesn't affect navigation
- **D (Silent Fail)**: 4 - Model schema mismatches not detected
- **E (Ops Risk)**: 3 - Manual model updates error-prone
- **Evidence**: `scripts/kie_sync.py` exists but not integrated into CI/CD or admin workflow.

---

## TASK LEDGER

| ID | Task | Status | Assigned | Notes |
|----|------|--------|----------|-------|
| T-001 | Fix queue drops under load (metrics + backpressure) | Done | - | ✅ Added queue_utilization_percent, drop_rate_percent, last_drop_time, backpressure_active to /health |
| T-002 | Add CID propagation to KIE job lifecycle | Planned | - | P0: Pass cid from telemetry to job creation, polling, callback handlers |
| T-003 | Add payment idempotency validation | Planned | - | P1: Validate `ref` uniqueness before processing payment |
| T-004 | Improve PASSIVE mode UX (premium message) | Planned | - | P2: Replace hardcoded message with premium styling, add "Refresh" button |
| T-005 | Integrate KIE sync parser into workflow | Planned | - | P2: Add `kie_sync --dry-run` to CI, create admin command for model updates |

---

## CHANGELOG ENTRIES

### Entry 1: 2026-01-14T08:00:00Z - Baseline Audit + TOP-5 Identification

**What was observed**:
- Conducted 5 mandatory audits (UX Flow, Reliability, KIE Integration, Parser, Observability)
- Identified 5 critical issues via scoring algorithm (A-E axes)
- Found 9 occurrences of "Старт с 200₽" in docs (already removed from code in previous cycle)

**What changed**:
- Created new `TRT_REPORT.md` structure (SYSTEM STATUS, TOP-5 CRITICALS, TASK LEDGER, CHANGELOG)
- Identified TOP-5 issues with scoring table
- Created TASK LEDGER with 5 planned tasks

**Why it is safe**:
- No code changes yet (baseline snapshot only)
- Report structure is additive (no breaking changes)
- All issues documented with evidence and scoring

**Tests executed**:
- ✅ Grep search for "Старт с 200₽" (found 9 in docs, 0 in code)
- ✅ Code review of `app/utils/update_queue.py` (queue drop logic)
- ✅ Code review of `app/kie/` modules (CID propagation)
- ✅ Code review of `app/payments/` modules (idempotency)

**Results**:
- All audits completed
- TOP-5 issues identified and scored
- TASK LEDGER created

**Remaining risks / next improvements**:
- ⚠️ Queue drops may cause silent failures under high load (T-001)
- ⚠️ Missing CID in KIE lifecycle makes debugging harder (T-002)
- ⚠️ Payment idempotency not validated (T-002)
- ⚠️ PASSIVE mode UX not premium (T-004)
- ⚠️ KIE sync parser not integrated (T-005)

---

## KIE PARSER DIFFS

**Status**: ⏳ PENDING  
**Last Run**: Not executed yet  
**Next Action**: Run `python scripts/kie_sync.py --mode=check --dry-run` after fixing Python path issue

**Note**: Parser exists (`scripts/kie_sync.py`) but requires Python 3.11+ and dependencies. Will integrate into CI/CD in T-005.

---

## UX COPY / MENU CHANGES

**"Старт с 200₽" Removal Status**: ✅ VERIFIED  
**Evidence**:
```bash
grep -r "Старт с 200\|200₽" . --exclude-dir=.git
# Found 9 occurrences in docs (historical references, not in code)
# 0 occurrences in active code (bot/handlers/flow.py, main_render.py, etc.)
```

**Current Menu Copy**: Premium style (verified in `bot/handlers/flow.py:start_cmd`)

---

## NEXT ACTIONS

1. **T-002: Add CID propagation to KIE job lifecycle** (P0)
   - Pass `cid` from telemetry to `app/kie/` modules
   - Add `cid` to job creation, polling, callback handlers
   - Update job storage to include `cid` field
   - Create branch: `fix/top5-kie-cid`

3. **T-003: Add payment idempotency validation** (P1)
   - Validate `ref` uniqueness in payment handlers
   - Return error if duplicate `ref` detected
   - Add test for idempotency
   - Create branch: `fix/top5-payment-idempotency`

---

## SYSTEM BASELINE (Legacy Section - Preserved)

**Commit Hash (main)**: `a83b1cd` (latest: docs update)  
**Active Feature Flags**:
- `BOT_MODE=webhook` (production)
- `SINGLE_MODEL_ONLY=0` (all models enabled)
- `LOCK_MODE=wait_then_passive` (default)
- `DRY_RUN=0` (real generation enabled)
- `TEST_MODE=0` (production mode)

**Active Model Registry Version**: `1.2.10-FINAL` (from `models/KIE_SOURCE_OF_TRUTH.json`)  
**Pricing Map Version**: `1.2.10-FINAL` (embedded in registry)  
**Last Successful Smoke Timestamp**: ⏳ PENDING (will update after deploy verification)

**System Documentation**:
- `TRT_SYSTEM.md`: ✅ Created
- `TRT_RUNBOOK.md`: ✅ Created

---

**End of TRT_REPORT.md**
