# TRT Production Hardening Report - Cycle 10 + Production Readiness

**Date**: 2026-01-XX  
**Branch**: `fix/production-readiness`  
**Status**: ✅ COMPLETED

---

## Nano-Banana-Pro Model Integration (Contract-Driven)

**Date**: 2026-01-XX  
**Model**: `nano-banana-pro`  
**Status**: ✅ COMPLETED

### Summary

Added nano-banana-pro model using contract-driven SSOT approach with:
- Full input schema with properties, required flags, enums, defaults, and constraints
- Resolution-based pricing rules (1K/2K = 18 credits, 4K = 24 credits)
- Vendor doc comparison tooling
- Smoke tests for payload building and pricing calculation

### Changes

#### 1. Vendor Documentation
- Created `kb/vendor_docs/nano-banana-pro.md` with raw vendor API documentation (verbatim)

#### 2. SSOT Update
- Updated `models/KIE_SOURCE_OF_TRUTH.json` for nano-banana-pro:
  - Added `properties` structure to `input_schema.input`:
    - `prompt` (required, string, max_length: 20000)
    - `image_input` (optional, array, max_items: 8)
    - `aspect_ratio` (optional, enum, default: "1:1")
    - `resolution` (optional, enum, default: "1K")
    - `output_format` (optional, enum, default: "png")
  - Added `pricing_rules`:
    ```json
    "pricing_rules": {
      "resolution": {"1K": 18, "2K": 18, "4K": 24},
      "strategy": "by_resolution"
    }
    ```

#### 3. Pricing Engine Update
- Updated `app/payments/pricing.py`:
  - Added support for `pricing_rules` in `calculate_kie_cost()`:
    - `strategy: "by_resolution"` - resolution-based pricing
    - `strategy: "by_duration"` - duration-based pricing (future)
  - Backward compatible: falls back to `pricing.credits_per_gen` if no pricing_rules

#### 4. Vendor Doc Comparison Tool
- Created `tools/compare_vendor_doc_to_ssot.py`:
  - Parses vendor docs from `kb/vendor_docs/*.md`
  - Compares against SSOT (endpoints, schema fields, enums, defaults, pricing_rules)
  - Outputs diff report (does NOT auto-mutate SSOT)

#### 5. Smoke Tests
- Created `tools/smoke_model_pipeline.py`:
  - Test 1: Defaults (1K resolution) → 18 credits
  - Test 2: Custom resolution (4K) → 24 credits
  - Test 3: Image input validation (max_items: 8)

### Verification Steps

1. **Run vendor doc comparison**:
   ```bash
   python tools/compare_vendor_doc_to_ssot.py
   ```
   Expected: ✅ MATCH - No differences found

2. **Run smoke tests**:
   ```bash
   python tools/smoke_model_pipeline.py
   ```
   Expected: ✅ All smoke tests passed

3. **Manual verification in bot**:
   - `/start` → choose "image" category → choose "nano-banana-pro"
   - Run with defaults → confirm 18 credits shown in preflight
   - Run with resolution 4K → confirm 24 credits shown in preflight
   - Check Render logs for correct credit deduction

### Files Changed

- `kb/vendor_docs/nano-banana-pro.md` (new)
- `models/KIE_SOURCE_OF_TRUTH.json` (updated)
- `app/payments/pricing.py` (updated)
- `tools/compare_vendor_doc_to_ssot.py` (new)
- `tools/smoke_model_pipeline.py` (new)
- `TRT_REPORT.md` (updated)

---

## Production Readiness Hardening - Final (Latest)

**Date**: 2026-01-XX  
**Branch**: `fix/p0-telemetry-safety`  
**Status**: ✅ COMPLETED

### Summary

Production readiness hardening focused on:
1. **P0 Bug Fixes**: Fixed callback.update_id usage, telemetry signature compatibility, exception middleware hardening
2. **PASSIVE Mode UX**: Ensured users get clear feedback during deploy overlap
3. **Smoke Tests**: Created automated smoke tests for webhook production readiness
4. **SSOT Validator**: Created tool to compare vendor docs against SSOT without auto-mutation

### P0 Bug Fixes

#### A) CallbackQuery.update_id Bug
- **Problem**: `AttributeError: 'CallbackQuery' object has no attribute 'update_id'` (bot/handlers/flow.py:1758)
- **Solution**: 
  - Created unified `get_event_ids(event, data)` function to safely extract ALL IDs at once
  - All handlers now use `get_event_ids()` instead of individual helpers
  - Helper safely extracts `update_id` from `data["event_update"].update_id` or `data["update"].update_id`
  - For callbacks, logs `callback.id` as `callback_id` and `update_id` as optional
  - **Guarantee**: Logging NEVER crashes even if fields are missing
- **Files Changed**:
  - `app/telemetry/telemetry_helpers.py` - Added `get_event_ids()` unified function
  - `app/telemetry/__init__.py` - Exported `get_event_ids`
  - `bot/handlers/flow.py` - Updated to use `get_event_ids()`
  - `bot/handlers/fallback.py` - Updated to use `get_event_ids()`
  - `bot/middleware/exception_middleware.py` - Updated to use `get_event_ids()`
  - `app/middleware/exception_middleware.py` - Updated to use `get_event_ids()`

#### B) log_callback_rejected Signature Mismatch
- **Problem**: `TypeError: log_callback_rejected() got unexpected keyword argument 'reason_detail'`
- **Solution**: 
  - `log_callback_rejected` has `reason_detail: Optional[str] = None` in signature
  - **All call sites updated** to use unified contract:
    - `reason_code` (preferred) or `reason` (backward compatible)
    - `reason_detail` (optional, for detailed error messages)
    - `error_type`, `error_message` (optional, for exceptions)
    - `cid` (correlation ID)
  - Added unit test: `tests/test_telemetry_contract.py` to verify signature compatibility
- **Files Changed**:
  - `app/telemetry/events.py` - Has correct signature with `reason_detail`
  - `bot/handlers/flow.py` - Updated to use unified contract
  - `bot/handlers/fallback.py` - Updated to use unified contract
  - `app/middleware/exception_middleware.py` - Updated to use unified contract
  - `bot/middleware/passive_mode_middleware.py` - Already uses correct contract
  - `tests/test_telemetry_contract.py` - New unit test

#### C) Exception Middleware Hardening
- **Problem**: Exception middleware must NEVER throw while handling an exception
- **Solution**:
  - Extract callback BEFORE any other operations
  - ALWAYS answer callback first (prevent infinite spinner)
  - All exception handling wrapped in try/except with ultimate fail-safes
  - Never re-raise exceptions from within exception handling
- **Files Changed**:
  - `bot/middleware/exception_middleware.py` - Hardened with fail-safe callbacks

### PASSIVE Mode UX

- **Problem**: PASSIVE mode "silently eats" clicks (PASSIVE_REJECT) - user sees infinite spinner
- **Solution**:
  - Implemented direct Telegram API calls in `update_queue.py` worker loop
  - When PASSIVE: worker calls `answerCallbackQuery()` or `sendMessage()` directly via HTTP
  - User ALWAYS gets feedback: "⏸️ Сервис перезапускается… попробуйте через 10–20 секунд"
  - **Guarantee**: Works even if aiogram dispatcher is broken
  - Logs: `PASSIVE_ACK_SENT` with `cid` and `update_id`
- **Files Changed**:
  - `app/utils/update_queue.py` - Added `_send_passive_ack()` function with direct Telegram API
  - `scripts/smoke_passive_ack.py` - Smoke test for PASSIVE mode UX

### Smoke Tests

- **Created**: `scripts/smoke_webhook.py`
  - Test 1: Import main_render.py without ImportError
  - Test 2: Create dp/bot without crashes
  - Test 3: Simulate callback event (cat:image) without AttributeError/TypeError
  - Test 4: Fallback handler responds to UNKNOWN_CALLBACK
  - Test 5: Telemetry function signatures are compatible
- **Makefile**: Added `smoke-webhook` and `smoke` targets

- **Created**: `scripts/e2e_smoke_all_buttons.py` (E2E "боевой" smoke)
  - Generates test matrix from SOURCE_OF_TRUTH: `model_id → required_inputs → defaults → validators`
  - Tests categories (cat:image, cat:enhance, etc.)
  - Tests model defaults application
  - Tests model validation
  - Tests required fields enforcement
  - **Guarantee**: One run gives "green/red" status for ALL buttons/models
  - Usage: `python scripts/e2e_smoke_all_buttons.py`

### SSOT Validator & Registry Diff Check

- **Created**: `scripts/validate_model_doc_against_ssot.py`
  - Parses vendor docs from `kb/vendor_docs/*.md`
  - Compares against SSOT (schema fields, enums, defaults, limits)
  - Outputs diff report (does NOT auto-mutate SSOT)
  - Usage: `python scripts/validate_model_doc_against_ssot.py <model_id> [doc_path]`

- **Created**: `scripts/registry_diff_check.py`
  - Compares incoming vendor docs with current SOURCE_OF_TRUTH
  - Checks all files in `kb/vendor_docs/*.md` by default
  - Outputs diff report without mutating SSOT
  - Usage: `python scripts/registry_diff_check.py [vendor_doc_path]`

### Verification Steps

#### Local Verification

1. **Run unit tests**:
   ```bash
   python -m pytest tests/test_telemetry_contract.py -v
   ```
   Expected: ✅ ALL TESTS PASSED

2. **Run smoke tests**:
   ```bash
   make smoke
   # or
   python scripts/smoke_webhook.py
   ```
   Expected: ✅ ALL TESTS PASSED

3. **Run E2E smoke test** (all buttons/models):
   ```bash
   python scripts/e2e_smoke_all_buttons.py
   ```
   Expected: ✅ Matrix generated, all tests passed

4. **Run registry diff check**:
   ```bash
   python scripts/registry_diff_check.py
   ```
   Expected: ✅ All vendor docs match SSOT

#### Telegram Bot Verification

1. **Test category buttons**:
   - `/start` → click "cat:image" → verify no exceptions
   - Click "cat:enhance" → verify models shown
   - Verify no `AttributeError` in logs

2. **Test fallback handler**:
   - Click unknown callback (e.g., `test:unknown`) → verify fallback responds
   - Verify `UNKNOWN_CALLBACK` logged with `cid`

3. **Test PASSIVE mode** (during deploy overlap):
   - Deploy twice quickly to trigger PASSIVE mode
   - Click any button → verify toast "⏸️ Сервис перезапускается…"
   - Verify no infinite spinner
   - Verify `PASSIVE_ACK_SENT` in logs

#### Render Logs Verification (after deploy)

**Look for these log patterns:**

1. **UPDATE_RECEIVED** (every update):
   ```
   📥 UPDATE_RECEIVED cid=... update_id=... user_id=... type=callback_query
   ```

2. **CALLBACK_RECEIVED** (every callback):
   ```
   🔘 CALLBACK_RECEIVED cid=... data='cat:image' query_id=... update_id=...
   ```

3. **DISPATCH_OK** (successful processing):
   ```
   ✅ DISPATCH_OK update_id=... cid=...
   ```

4. **PASSIVE_ACK_SENT** (PASSIVE mode feedback):
   ```
   ✅ PASSIVE_ACK_SENT type=callback_query update_id=... cid=... data=cat:image
   ```

5. **UNKNOWN_CALLBACK** (fallback handler):
   ```
   ⚠️ CALLBACK_REJECTED cid=... reason=UNKNOWN_CALLBACK reason_detail=...
   ```

6. **EXCEPTION_MIDDLEWARE** (error handling):
   ```
   ❌ UNHANDLED EXCEPTION: ... cid=... update_id=...
   ```

**Verify NO errors:**
- ❌ NO `AttributeError: 'CallbackQuery' object has no attribute 'update_id'`
- ❌ NO `TypeError: log_callback_rejected() got unexpected keyword argument 'reason_detail'`
- ❌ NO silent clicks (every callback should have `CALLBACK_RECEIVED` + `DISPATCH_OK` or `CALLBACK_REJECTED`)

#### Health Endpoints

- `GET /health` → should return 200
- `GET /` → should return 200

### Files Changed

**P0 Fixes:**
- `app/telemetry/telemetry_helpers.py` - Added `get_event_ids()` unified function
- `app/telemetry/__init__.py` - Exported `get_event_ids`
- `bot/handlers/flow.py` - Updated to use `get_event_ids()` and unified contract
- `bot/handlers/fallback.py` - Updated to use `get_event_ids()` and unified contract
- `bot/middleware/exception_middleware.py` - Updated to use `get_event_ids()`
- `app/middleware/exception_middleware.py` - Updated to use `get_event_ids()` and unified contract
- `tests/test_telemetry_contract.py` - New unit test for telemetry contract

**PASSIVE Mode UX:**
- `app/utils/update_queue.py` - Added `_send_passive_ack()` with direct Telegram API
- `scripts/smoke_passive_ack.py` - Smoke test for PASSIVE mode UX

**E2E Smoke Tests:**
- `scripts/e2e_smoke_all_buttons.py` - E2E smoke test for all buttons/models matrix
- `scripts/smoke_webhook.py` - Webhook production readiness smoke test
- `Makefile` - Added smoke-webhook and smoke targets

**Registry Tools:**
- `scripts/registry_diff_check.py` - Compares vendor docs with SSOT
- `scripts/validate_model_doc_against_ssot.py` - Validates specific model docs

**Documentation:**
- `TRT_REPORT.md` - Updated with complete verification steps

---

## Kie Sync Parser (Latest)

**Date**: 2026-01-XX  
**Branch**: `feat/kie-sync-parser`  
**Status**: ✅ COMPLETED

### Summary

Created safe Kie.ai documentation sync module for syncing upstream documentation with local SOURCE_OF_TRUTH without breaking existing contracts.

### Features

1. **Safe Parser** (`app/kie_sync/parser.py`):
   - Extracts model_id from JSON/cURL examples
   - Extracts endpoints (standard or overrides)
   - Extracts input schema from tables/JSON
   - Extracts pricing (USD/credits)
   - Caching with checksums (no re-fetch if unchanged)
   - Rate limiting (1 rps, retries, timeout)

2. **Safe Reconciler** (`app/kie_sync/reconciler.py`):
   - NEVER deletes existing fields
   - NEVER changes required→optional automatically
   - Adds new fields as `experimental=true` and optional
   - Adds new models as `disabled=true`
   - Pricing: `RUB = USD * 78 * 2` (fixed formula)

3. **CLI** (`scripts/kie_sync.py`):
   - `pull` - Fetch pages and cache HTML
   - `build` - Build normalized upstream JSON
   - `reconcile` - Merge upstream into local registry
   - `--no-write` - Dry run mode

4. **Tests** (`tests/test_kie_parser.py`):
   - Unit tests for parser functions
   - Fixtures: nano-banana-pro, flux-2/pro-image-to-image, bytedance/v1-pro-fast-image-to-video
   - Golden-file test for stable output

### Files Changed

- `app/kie_sync/__init__.py` - Module initialization
- `app/kie_sync/config.py` - Configuration (paths, pricing constants, network settings)
- `app/kie_sync/parser.py` - HTML parser with BeautifulSoup
- `app/kie_sync/reconciler.py` - Safe merge logic
- `app/kie_sync/cli.py` - CLI commands
- `scripts/kie_sync.py` - CLI wrapper script
- `tests/test_kie_parser.py` - Unit tests
- `tests/fixtures/kie_pages/*.html` - Test fixtures (3 pages)
- `generated/kie_upstream.json.example` - Example output
- `Makefile` - Added `kie-sync`, `kie-sync-pull`, `kie-sync-build`, `kie-sync-reconcile` targets
- `requirements.txt` - Added `beautifulsoup4>=4.12.0`, `lxml>=4.9.0`
- `README.md` - Added "Обновление моделей/параметров/цен" section
- `TRT_REPORT.md` - Updated with Kie Sync section

### Usage

```bash
# Pull fresh data (with network)
make kie-sync-pull

# Build upstream JSON (from cache or network)
make kie-sync-build

# Reconcile with local registry (dry-run)
make kie-sync-reconcile

# Apply changes (after reviewing diff)
python scripts/kie_sync.py reconcile
```

### Safety Guarantees

- ✅ No deletions of existing fields
- ✅ No automatic required/optional changes
- ✅ New fields marked as experimental
- ✅ New models disabled by default
- ✅ Pricing formula: `RUB = USD * 78 * 2` (fixed)
- ✅ Dry-run mode for safe testing
- ✅ Checksum-based caching (no re-fetch if unchanged)

### Verification

```bash
# Run parser tests
python -m pytest tests/test_kie_parser.py -v

# Run sync on fixtures (no network)
make kie-sync

# Check diff (dry-run)
python scripts/kie_sync.py reconcile --no-write
```

---

## Original Cycle 10 Report

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

