# Cycle 9 Phase 2: 10 P0 Tasks

**Auto-discovered**: 2026-01-13 18:15 UTC  
**Mode**: TRT FINISHER  
**Goal**: Complete telemetry integration + smoke tests

---

## Task List (P0 Priority)

### 1. ✅ HOTFIX: Fix StreamHandler import (DONE)
- **Status**: COMMITTED (7a37cbd)
- **Impact**: Unblocked Render deployment

### 2. 🔄 Integrate telemetry into balance.py handlers (IN PROGRESS)
- **File**: `bot/handlers/balance.py`
- **Handlers**: 5 callback handlers without telemetry
- **Impact**: Balance/topup flow unobservable

### 3. ⏳ Integrate telemetry into z_image.py handler
- **File**: `bot/handlers/z_image.py`
- **Handlers**: z-image flow (SINGLE_MODEL mode)
- **Impact**: Main generation flow unobservable

### 4. ⏳ Integrate telemetry into admin.py handlers
- **File**: `bot/handlers/admin.py`
- **Handlers**: 8+ admin callbacks
- **Impact**: Admin operations unobservable

### 5. ⏳ Integrate telemetry into history.py handler
- **File**: `bot/handlers/history.py`
- **Impact**: Generation history unobservable

### 6. ⏳ Integrate telemetry into marketing.py handler
- **File**: `bot/handlers/marketing.py`
- **Impact**: Referral/promo unobservable

### 7. ⏳ Integrate telemetry into gallery.py handler
- **File**: `bot/handlers/gallery.py`
- **Impact**: Gallery view unobservable

### 8. ⏳ Integrate telemetry into quick_actions.py handler
- **File**: `bot/handlers/quick_actions.py`
- **Impact**: Quick shortcuts unobservable

### 9. ⏳ Add PASSIVE mode rejection UX (no silent failures)
- **File**: All handlers
- **Requirement**: answerCallbackQuery with reason when PASSIVE
- **Impact**: Users see "❌ Bot busy, retry" instead of silence

### 10. ⏳ Run smoke_buttons_instrumentation.py and verify
- **File**: `scripts/smoke_buttons_instrumentation.py`
- **Requirement**: All event chains must work
- **Impact**: CI gate for future deploys

---

## Execution Plan

**Order**: 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

**Commits**: Small, per-handler commits

**Testing**: After each handler, verify import works locally

**Deployment**: After task 10, push to main
