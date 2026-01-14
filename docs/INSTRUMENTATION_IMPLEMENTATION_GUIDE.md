# Instrumentation Implementation Guide

**Status**: P0 Task - Foundation Complete, Ready for Integration  
**Goal**: Integrate telemetry into existing handlers  
**Effort**: 2-3 hours for full integration  
**CI Blocking**: Smoke test gates future deploys until integrated

---

## Phase 1: Setup (Done ✅)

Infrastructure is in place:
- ✅ `app/telemetry/logging_contract.py` - Core log_event, ReasonCode, EventType
- ✅ `app/telemetry/ui_registry.py` - ScreenId, ButtonId, UIMap (SSOT)
- ✅ `app/telemetry/telemetry_helpers.py` - Helper functions
- ✅ `app/handlers/debug_handler.py` - /debug command for admin
- ✅ `app/telemetry/logging_config.py` - JSON/KV formatting
- ✅ `scripts/smoke_buttons_instrumentation.py` - Smoke test

---

## Phase 2: Integration Checklist

### 1. Update Main App Initialization

**File**: `main.py` or app entry point

```python
# Add imports
from app.telemetry.logging_config import configure_logging
from app.telemetry.telemetry_helpers import TelemetryMiddleware

# Early in startup
async def main():
    # Configure logging (JSON format for Render)
    configure_logging()
    
    # Register middleware
    dp = Dispatcher(...)
    dp.message.middleware(TelemetryMiddleware())
    dp.callback_query.middleware(TelemetryMiddleware())
    
    # Register /debug command handler
    from app.handlers.debug_handler import cmd_debug, cb_debug_*
    router.message.register(cmd_debug, commands=["debug"])
    router.callback_query.register(cb_debug_on_30, F.data == "debug_on_30")
    router.callback_query.register(cb_debug_show_last_cid, F.data == "debug_show_last_cid")
    router.callback_query.register(cb_debug_close, F.data == "debug_close")
```

**ENV to add**:
```bash
LOG_FORMAT=json               # or "kv"
LOG_LEVEL=INFO                # or DEBUG if debug enabled
SILENCE_GUARD=true            # Warn if callback has no result logged
```

### 2. Update Callback Handlers

**Template** (see `docs/telemetry_integration_example.md` for full example):

```python
from aiogram import types
from app.telemetry.telemetry_helpers import (
    log_callback_received,
    log_callback_routed,
    log_callback_accepted,
    log_callback_rejected,
    log_ui_render,
    log_answer_callback_query,
)
from app.telemetry import ReasonCode, ScreenId, ButtonId

@router.callback_query(F.data.startswith("action="))
async def handle_category_select(callback: types.CallbackQuery, **kwargs):
    # 1. Setup
    cid = kwargs.get("cid")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # 2. Log CALLBACK_RECEIVED
    log_callback_received(cid, callback.update_id, user_id, chat_id, callback.data, "ACTIVE")
    
    # 3. Parse callback_data
    try:
        action, category_id = parse_callback(callback.data)
    except ValueError:
        log_callback_rejected(
            cid, user_id, chat_id,
            reason_code=ReasonCode.CALLBACK_PARSE_ERROR,
            reason_text="Invalid callback format"
        )
        await callback.answer("❌ Invalid button", show_alert=True)
        return
    
    # 4. Log CALLBACK_ROUTED
    log_callback_routed(cid, user_id, chat_id, __name__, "category", button_id=ButtonId.CAT_IMAGE)
    
    # 5. Validate FSM state
    user_state = await fsm.get_state(user_id)
    if user_state != ScreenId.MAIN_MENU:
        log_callback_rejected(
            cid, user_id, chat_id,
            reason_code=ReasonCode.STATE_MISMATCH,
            reason_text="User on wrong screen",
            expected_state=ScreenId.MAIN_MENU,
            actual_state=user_state
        )
        await callback.answer("❌ Button expired, use /start")
        return
    
    # 6. Process
    try:
        models = await db.get_models_for_category(category_id)
        await fsm.set_state(user_id, ScreenId.MODEL_PICK)
        keyboard = build_keyboard(models)
    except Exception as e:
        log_callback_rejected(
            cid, user_id, chat_id,
            reason_code=ReasonCode.DB_ERROR,
            reason_text=f"Error fetching models: {str(e)[:100]}"
        )
        await callback.answer("❌ Server error, try again")
        return
    
    # 7. Log CALLBACK_ACCEPTED
    log_callback_accepted(cid, user_id, chat_id, ScreenId.MODEL_PICK)
    
    # 8. Send UI
    await callback.message.edit_text("Select model:", reply_markup=keyboard)
    
    # 9. Log UI_RENDER
    log_ui_render(cid, user_id, chat_id, ScreenId.MODEL_PICK, [m.button_id for m in models])
    
    # 10. Answer callback
    log_answer_callback_query(cid, user_id, chat_id, "✅ Models loaded")
    await callback.answer("✅ Models loaded")
```

**Files to update** (priority order):
1. Handler for category selection
2. Handler for model selection
3. Handler for parameter inputs
4. Handler for confirmation
5. Handler for BACK button
6. Handler for /start command

### 3. Update Parameter Handlers

**For text input** (prompts, etc.):

```python
from app.telemetry.telemetry_helpers import (
    log_param_input,
    log_param_validation_failed,
)

async def process_user_text(message: types.Message, **kwargs):
    cid = kwargs.get("cid")
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    param_name = "prompt_text"
    value = message.text
    
    # Log input
    log_param_input(cid, user_id, chat_id, param_name, value, source="text")
    
    # Validate
    if len(value) < 5:
        log_param_validation_failed(
            cid, user_id, chat_id,
            param_name=param_name,
            reason_code=ReasonCode.VALIDATION_FAILED,
            hint_to_user="Prompt must be at least 5 characters"
        )
        await message.reply_text("❌ Prompt too short (min 5 chars)")
        return
    
    # Save & continue
    await fsm.set_data(user_id, {param_name: value})
    log_param_accepted(cid, user_id, chat_id, param_name, value)  # (optional helper)
```

### 4. Update Queue/Dispatch

**If using async queue** (see `app/utils/update_queue.py`):

```python
from app.telemetry.telemetry_helpers import (
    log_queue_enqueue,
    log_queue_pick,
    log_dispatch_start,
    log_dispatch_ok,
    log_dispatch_fail,
)

# On enqueue
async def enqueue_update(update: Update, cid: str):
    log_queue_enqueue(cid, update.update_id, "callback_query", queue.qsize())
    queue.put((update, cid))

# In worker
async def worker():
    while True:
        update, cid = queue.get()
        
        # Log pick
        log_queue_pick(cid, worker_id=f"worker_{os.getpid()}")
        
        # Log dispatch
        timer = log_dispatch_start(cid)
        try:
            await dispatcher.feed_update(update)
            log_dispatch_ok(cid, timer)
        except Exception as e:
            log_dispatch_fail(cid, timer, type(e).__name__, str(e))
```

### 5. Register /debug Command

**In router setup** (e.g., where other commands registered):

```python
from app.handlers.debug_handler import (
    cmd_debug,
    cb_debug_on_30,
    cb_debug_show_last_cid,
    cb_debug_close,
)

# Message commands
router.message.register(cmd_debug, commands=["debug"])

# Callback queries
router.callback_query.register(cb_debug_on_30, F.data == "debug_on_30")
router.callback_query.register(cb_debug_show_last_cid, F.data == "debug_show_last_cid")
router.callback_query.register(cb_debug_close, F.data == "debug_close")
```

---

## Phase 3: Testing

### Smoke Test

Run locally:
```bash
cd /workspaces/TRT
python scripts/smoke_buttons_instrumentation.py
```

Expected output:
```
✅ CALLBACK_RECEIVED: found
✅ CALLBACK_ROUTED: found
✅ CALLBACK_ACCEPTED: found
✅ UI_RENDER: found
✅ PASS: Full callback chain detected
```

### Manual Testing

1. Start bot with `LOG_FORMAT=json`
2. Send /start
3. Click button
4. Check logs for cid chain:
   ```
   {"ts": "...", "name": "CALLBACK_RECEIVED", "cid": "a1b2c3d4", ...}
   {"ts": "...", "name": "CALLBACK_ROUTED", "cid": "a1b2c3d4", ...}
   {"ts": "...", "name": "CALLBACK_ACCEPTED", "cid": "a1b2c3d4", ...}
   {"ts": "...", "name": "UI_RENDER", "cid": "a1b2c3d4", ...}
   ```

### Test Rejection Scenarios

```bash
# 1. PASSIVE_REJECT: Start second instance, click button
# Expected: reason_code=PASSIVE_REJECT, reason_text="Instance not ACTIVE"

# 2. STATE_MISMATCH: Go to /start, then curl callback with wrong FSM state
# Expected: reason_code=STATE_MISMATCH, expected_state=MAIN_MENU, actual_state=...

# 3. VALIDATION_FAILED: Send invalid parameter
# Expected: reason_code=VALIDATION_FAILED, reason_text="Invalid value"
```

---

## Phase 4: Verification (60-second Diagnosis)

### Find by CID

User reports: "Button doesn't work"

1. Get cid from `/debug` panel (last CID button)
2. In Render logs, search: `cid=a1b2c3d4`
3. See entire chain:
   ```
   CALLBACK_RECEIVED ✅
   CALLBACK_ROUTED ✅
   CALLBACK_ACCEPTED ❌ reason_code=STATE_MISMATCH
   ANSWER_CALLBACK_QUERY "Button expired, use /start"
   ```
4. **Diagnosis**: "User was on wrong screen, need to reset with /start"
5. **Action**: Tell user to use /start or provide button to reset

### Find by Reason Code

Search: `reason_code=PASSIVE_REJECT`

Results show all instances when buttons didn't work because bot was PASSIVE.

### Find by Domain

Search: `domain=UX` to see all UI-related events
Search: `domain=DB_ERROR` to see all database issues

---

## Common Patterns

### Pattern 1: Validate then Process

```python
# ✅ GOOD
try:
    validate_input()
    log_param_input()
    process()
    log_callback_accepted()
except ValidationError:
    log_param_validation_failed()
    notify_user()
```

### Pattern 2: Early Exit with Reason

```python
# ✅ GOOD
if condition_fails:
    log_callback_rejected(reason_code=X, reason_text="...")
    await callback.answer(user_text)
    return  # Early exit, one place

# ❌ BAD
if condition_fails:
    await callback.answer(user_text)
    return  # No log - silent failure!
```

### Pattern 3: Always Answer Callback

```python
# ✅ GOOD
try:
    process()
    log_answer_callback_query(cid, user_id, chat_id, "✅ Done")
    await callback.answer("✅ Done")
except:
    log_answer_callback_query(cid, user_id, chat_id, "❌ Error")
    await callback.answer("❌ Error", show_alert=True)

# ❌ BAD
try:
    process()
except:
    return  # No answer - Telegram UI hangs for user!
```

---

## Rollout Plan

**Week 1**:
- Update 3-5 main handlers (start, category, model, params, confirm)
- Test with smoke_buttons_instrumentation.py
- Run in staging, verify logs

**Week 2**:
- Update remaining handlers (back, cancel, retry)
- Test rejection scenarios
- Update /debug command to show actual events

**Week 3**:
- Deploy to production
- Monitor `/debug` output
- Collect first real user issue → verify 60-second diagnosis works

**Week 4**:
- Full documentation review
- Training for team on using cid for diagnostics
- Iterate based on production feedback

---

## Success Criteria

By end of integration, you can:

1. **User reports "button X doesn't work"**
   - Admin: Get cid from /debug
   - Admin: Search logs for cid=X
   - Find: CALLBACK_RECEIVED → CALLBACK_ROUTED → CALLBACK_REJECTED (reason_code)
   - Diagnosis: Done in <60 seconds ✅

2. **Search by reason_code**
   - `reason_code=STATE_MISMATCH` → find all wrong-screen clicks
   - `reason_code=DB_ERROR` → find all database issues
   - Pattern analysis works ✅

3. **Zero silent failures**
   - Every rejected callback logged with reason
   - Every parameter validation failure tracked
   - Admin can audit all failures in production ✅

---

## Questions?

Refer to:
- [docs/telemetry.md](../docs/telemetry.md) - Specification
- [docs/telemetry_integration_example.md](../docs/telemetry_integration_example.md) - Code examples
- [app/telemetry/__init__.py](../app/telemetry/__init__.py) - Available imports

---

**Target**: All handlers integrated by end of Cycle 9.  
**CI Gating**: Smoke test blocks merges until integrated.  
**Owner**: Principal Engineer (setup complete, integration in progress).
