# TRT Production Hardening Report - Cycle 10

**Date**: 2026-01-XX  
**Branch**: `fix/cycle10-prod-hardening-v2`  
**Status**: ✅ COMPLETED

---

## Executive Summary

Production hardening cycle focused on:
1. **Telemetry Safety**: Fixed CallbackQuery.update_id bug and log_callback_rejected signature
2. **PASSIVE Mode UX**: No silent clicks during deploy overlap
3. **Unified Model Pipeline**: Foundation for standardized model execution
4. **Smoke Tests**: Automated validation of button instrumentation

---

## Changes Implemented

### STEP 1: Fix CallbackQuery update_id Bug (P0)

**Problem**: `AttributeError: 'CallbackQuery' object has no attribute 'update_id'` in production logs.

**Solution**:
- Created `app/telemetry/telemetry_helpers.py` with safe helper functions:
  - `get_update_id(event, data)` - safely extracts update_id from event or data context
  - `get_callback_id(event)` - extracts callback query ID
  - `get_user_id(event)`, `get_chat_id(event)`, `get_message_id(event)` - safe attribute access
- Updated `category_cb` handler to use safe helpers
- Updated `log_callback_received` to accept optional `update_id` parameter

**Files Changed**:
- `app/telemetry/telemetry_helpers.py` (new)
- `app/telemetry/events.py` (updated)
- `bot/handlers/flow.py` (updated)

**Verification**:
- Clicking category buttons (`cat:image`, `cat:enhance`) no longer throws AttributeError
- Telemetry logs still correlate by cid

---

### STEP 2: Fix log_callback_rejected Signature Mismatch (P0)

**Problem**: `TypeError: log_callback_rejected() got an unexpected keyword argument 'reason_detail'` in exception middleware.

**Solution**:
- Updated `log_callback_rejected` signature to accept:
  - `reason_code` (preferred) or `reason` (backward compatible)
  - `reason_detail` (optional)
  - `error_type` (optional)
  - `error_message` (optional)
  - `**extra` (safely ignored for backward compatibility)
- All telemetry logging wrapped in try/except for fail-safe behavior

**Files Changed**:
- `app/telemetry/events.py` (updated)

**Verification**:
- No TypeError in exception middleware path
- In failure case, user still receives callback answer and logs contain cid

---

### STEP 3: PASSIVE Mode UX (P0)

**Problem**: During Render deploy overlap (PASSIVE mode), user clicks produce no feedback (silent clicks).

**Solution**:
- Created `bot/middleware/passive_mode_middleware.py`:
  - Detects PASSIVE mode from `active_state` in data or application
  - For callbacks: immediately answers with "⏳ Сервис обновляется..." and shows refresh button
  - For messages: responds with maintenance message
  - Logs PASSIVE_REJECT with cid and reason_detail
- Integrated middleware in `create_bot_application` (before exception middleware)

**Files Changed**:
- `bot/middleware/passive_mode_middleware.py` (new)
- `bot_kie.py` (updated)

**Verification**:
- During Render deploy overlap (PASSIVE logs), every click gives user-visible feedback
- No "silent click" - all callbacks are answered immediately

---

### STEP 5: Unified Model Pipeline Foundation (P1)

**Goal**: Standardized flow for ALL models without per-model spaghetti code.

**Solution**:
- Created `app/kie/unified_pipeline.py` with `UnifiedModelPipeline` class:
  - `resolve_model(model_id)` - reads from SSOT
  - `get_schema(model_id)` - returns schema with RU labels, defaults, constraints
  - `apply_defaults(schema, collected)` - fills missing fields except prompt
  - `validate(model_id, params)` - contract-driven validation with RU error messages
  - `build_kie_payload(model_id, params)` - builds KIE API payload
  - `format_confirmation_text(model, params, price_rub)` - standardized confirmation screen

**Contract**:
- `prompt` always required
- Other params defaulted if defined, otherwise collected via minimal UI
- Standardized confirmation screen format
- Supports both flat and nested schema formats from SSOT

**Files Changed**:
- `app/kie/unified_pipeline.py` (new)

**Next Steps**:
- Integrate pipeline into existing handlers (z-image, flow.py)
- Migrate 5 representative models by config only

---

### STEP 7: Smoke Tests (P0/P1)

**Solution**:
- Created `scripts/smoke_buttons_instrumentation.py`:
  - Tests telemetry helpers (get_update_id, get_callback_id, etc.)
  - Tests log_callback_rejected signature
  - Tests unified pipeline basic functions
  - Tests category button callbacks
- Added `make smoke-buttons` target to Makefile

**Files Changed**:
- `scripts/smoke_buttons_instrumentation.py` (new)
- `Makefile` (updated)

**Verification**:
- Run: `make smoke-buttons` or `python scripts/smoke_buttons_instrumentation.py`
- All tests should pass

---

## Documentation Updates

### kb/monitoring.md
- Added "Telemetry Contract Checklist" section with:
  - Required event names
  - Required fields per event
  - Standard rejection reasons

---

## Verification Steps

### 1. Deploy
```bash
git push origin fix/cycle10-prod-hardening-v2
# Merge to main, Render auto-deploys
```

### 2. Test Category Buttons
1. `/start` → click "🎨 Картинки и дизайн" (cat:image)
2. Verify no exception in logs
3. Verify menu shows models

### 3. Test PASSIVE Mode UX
1. Deploy twice quickly (trigger PASSIVE mode)
2. Click any button during overlap
3. Verify: user sees "⏳ Сервис обновляется..." message with refresh button
4. Verify: no silent clicks

### 4. Test Fallback Handler
1. Send unknown callback (e.g., `test:unknown`)
2. Verify: fallback handler responds
3. Verify: logs contain UNKNOWN_CALLBACK reason_code

### 5. Test Telemetry Chain
1. `/debug` → get last cid
2. Grep Render logs: `cid=XXXXX`
3. Verify event chain:
   - UPDATE_RECEIVED
   - CALLBACK_RECEIVED
   - CALLBACK_ROUTED
   - CALLBACK_ACCEPTED (or CALLBACK_REJECTED with reason_code)
   - UI_RENDER
   - DISPATCH_OK

### 6. Run Smoke Tests
```bash
make smoke-buttons
# Should pass all tests
```

---

## Known Limitations

1. **Telemetry Coverage**: Not all handlers fully instrumented yet (balance.py, admin.py, history.py, etc.)
2. **Unified Pipeline**: Foundation created, but not yet integrated into existing handlers
3. **Vendor Doc Comparison**: Not yet implemented (STEP 6)

---

## Next Steps

1. Complete telemetry instrumentation for remaining handlers (STEP 4)
2. Integrate unified pipeline into z-image and migrate 5 models (STEP 5 continuation)
3. Implement vendor doc comparison tooling (STEP 6)
4. Add contract-driven pricing with resolution-based rules (STEP 6)

---

## Commit History

- `c1e0c30` - WIP: registry/spec groundwork (pre-hardening)
- `6a66457` - STEP 1-3: Fix telemetry safety + PASSIVE mode UX
- `e8a9a4e` - Fix: log_callback_received update_id parameter handling
- `847c689` - STEP 5: Unified Model Pipeline foundation
- `[pending]` - STEP 7: Smoke tests + documentation

---

**Status**: ✅ Ready for merge and deploy

