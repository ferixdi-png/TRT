# Instrumentation & Telemetry Contract

**Status**: MVP Implemented (P0 Priority)  
**Goal**: Diagnose "button not working" issues in 60 seconds from logs  
**Date**: 2026-01-13

---

## Overview

Product is now fully "instrumented" — every button click, parameter selection, and error produces a structured event log. Events are linked by `correlation_id` (cid), allowing developers to reconstruct the entire user journey.

**Key principle**: NO SILENT FAILURES. Every rejected callback, invalid input, state mismatch is logged with a reason code.

---

## Core Concepts

### 1. Correlation ID (CID)

Every user action produces a unique **correlation_id** (8-char UUID):

```
cid=a1b2c3d4
```

This single ID links all events for one button click:
```
[a1b2c3d4] CALLBACK_RECEIVED → CALLBACK_ROUTED → CALLBACK_ACCEPTED → UI_RENDER
```

**Usage**: Paste `cid=a1b2c3d4` into Render logs search to see entire flow.

### 2. Reason Codes

When something fails, a **reason_code** explains why:

| Code | Meaning | Action |
|------|---------|--------|
| `PASSIVE_REJECT` | Bot not ACTIVE (another instance) | Wait for active instance |
| `UNKNOWN_ACTION` | callback_data malformed | Check callback format |
| `STATE_MISMATCH` | FSM state wrong | User on wrong screen |
| `VALIDATION_FAILED` | Parameter invalid | Show hint to user |
| `RATE_LIMIT` | Too many requests | Throttle user |
| `DOWNSTREAM_TIMEOUT` | KIE.ai slow | Retry with timeout |
| `DOWNSTREAM_ERROR` | KIE.ai failed | Log error, offer retry |
| `DB_ERROR` | PostgreSQL error | Alert admin |
| `INTERNAL_ERROR` | Code bug | Stack trace in logs |

### 3. Event Types

Structured log events with JSON (one event = one line):

```json
{
  "ts": "2026-01-13T10:30:45.123Z",
  "name": "CALLBACK_ACCEPTED",
  "cid": "a1b2c3d4",
  "event_type": "callback_query",
  "update_id": 12345,
  "user_hash": "hash_user_123",
  "chat_hash": "hash_chat_456",
  "bot_state": "ACTIVE",
  "domain": "UX",
  "screen_id": "CATEGORY_PICK",
  "button_id": "CAT_IMAGE",
  "action_id": "category",
  "result": "accepted",
  "reason_code": "SUCCESS"
}
```

---

## Event Chain (Full Flow)

### Successful Button Click

```
1. CALLBACK_RECEIVED
   - Button data received from Telegram
   - payload_sanitized: first 100 chars of callback_data

2. CALLBACK_ROUTED
   - callback_data parsed
   - Handler identified
   - button_id extracted

3. CALLBACK_ACCEPTED
   - FSM state valid
   - Parameters parsed
   - next_screen determined

4. UI_RENDER
   - New screen sent to user
   - buttons list logged
```

All with **same cid** → traceable in logs.

### Rejected Button Click (Example: State Mismatch)

```
1. CALLBACK_RECEIVED
   - Button data received

2. CALLBACK_ROUTED
   - Handler identified

3. CALLBACK_REJECTED
   - reason_code: STATE_MISMATCH
   - reason_text: "FSM state was PARAMS_FORM, expected MAIN_MENU"
   - expected_state: MAIN_MENU
   - actual_state: PARAMS_FORM

4. ANSWER_CALLBACK_QUERY
   - Notify user: "Button expired, go back to menu"
```

---

## UI Map (SSOT)

All screens, buttons, transitions defined in [app/telemetry/ui_registry.py](../app/telemetry/ui_registry.py):

```python
class ScreenId(str, Enum):
    MAIN_MENU = "MAIN_MENU"
    CATEGORY_PICK = "CATEGORY_PICK"
    MODEL_PICK = "MODEL_PICK"
    PARAMS_FORM = "PARAMS_FORM"
    PROCESSING = "PROCESSING"
    RESULT = "RESULT"

class ButtonId(str, Enum):
    CAT_IMAGE = "CAT_IMAGE"
    CAT_VIDEO = "CAT_VIDEO"
    MODEL_ZIMAGE = "MODEL_ZIMAGE"
    CONFIRM_RUN = "CONFIRM_RUN"
```

**Validation**: `UIMap.is_valid_button_on_screen(screen_id, button_id)` prevents impossible buttons from being logged.

---

## Logging Contract

### Core Function

```python
from app.telemetry import log_event, ReasonCode, Domain

log_event(
    "CALLBACK_RECEIVED",
    correlation_id=cid,
    event_type="callback_query",
    update_id=update.update_id,
    user_id=user.id,
    chat_id=chat.id,
    bot_state="ACTIVE",
    domain=Domain.UX,
    button_id="CAT_IMAGE",
    payload_sanitized="action=category&id=1",
)
```

**Safety**: `user_id` and `chat_id` auto-hashed (no PII in logs).

### Helper Functions

```python
from app.telemetry.telemetry_helpers import (
    log_callback_received,
    log_callback_routed,
    log_callback_accepted,
    log_callback_rejected,
    log_ui_render,
    log_param_input,
    log_queue_enqueue,
)

# Simpler to use:
log_callback_accepted(
    cid=cid,
    user_id=user_id,
    chat_id=chat_id,
    next_screen="CATEGORY_PICK",
)
```

---

## Integration Points

### 1. Callback Handler (Routed)

```python
@router.callback_query(F.data.startswith("action="))
async def handle_category_select(callback: types.CallbackQuery, **kwargs):
    cid = kwargs.get("cid")  # From middleware
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    # Log reception
    log_callback_received(cid, update_id, user_id, chat_id, callback.data, "ACTIVE")
    
    # Parse callback_data
    try:
        action, category_id = callback.data.split("&")
    except:
        log_callback_rejected(
            cid, user_id, chat_id,
            reason_code=ReasonCode.CALLBACK_PARSE_ERROR,
            reason_text="Invalid callback format"
        )
        await callback.answer("❌ Invalid button", show_alert=True)
        return
    
    # Log routing
    log_callback_routed(cid, user_id, chat_id, handler=__name__, action_id="category")
    
    # FSM validation
    if user_state != "MAIN_MENU":
        log_callback_rejected(
            cid, user_id, chat_id,
            reason_code=ReasonCode.STATE_MISMATCH,
            reason_text=f"Expected MAIN_MENU, got {user_state}",
            expected_state="MAIN_MENU",
            actual_state=user_state,
        )
        await callback.answer("❌ Button expired, go to /start")
        return
    
    # Success
    log_callback_accepted(cid, user_id, chat_id, next_screen="CATEGORY_PICK")
    
    # Render next screen
    log_ui_render(cid, user_id, chat_id, "CATEGORY_PICK", ["MODEL_ZIMAGE", "BACK"])
    await send_models_menu(callback.message)
```

### 2. Parameter Validation

```python
log_param_input(
    cid=cid,
    user_id=user_id,
    chat_id=chat_id,
    param_name="aspect_ratio",
    value="16:9",
    source="button"
)

# If invalid:
log_param_validation_failed(
    cid=cid,
    user_id=user_id,
    chat_id=chat_id,
    param_name="aspect_ratio",
    reason_code=ReasonCode.VALIDATION_FAILED,
    hint_to_user="Valid: 16:9, 1:1, 4:3"
)
```

### 3. Queue & Dispatch

```python
# When enqueue
log_queue_enqueue(cid, update_id, "callback_query", queue.qsize())

# When worker picks
log_queue_pick(cid, worker_id="worker_1")

# During dispatch
timer = log_dispatch_start(cid)
try:
    result = await handler(...)
    log_dispatch_ok(cid, timer)
except Exception as e:
    log_dispatch_fail(cid, timer, type(e).__name__, str(e))
```

---

## /debug Command (Admin Only)

Available at `/debug` (only for `ADMIN_ID`).

**Shows**:
- Current bot mode (ACTIVE/PASSIVE)
- last_10_events summary with cid + screen + reason
- Last correlation_id (for pasting into logs search)

**Buttons**:
- "🔴 Enable Debug (30m)" — turn on DEBUG level logs
- "📋 Show Last CID" — copy last cid to clipboard
- "❌ Close" — hide debug panel

**Usage**:
1. User reports "button doesn't work"
2. Admin clicks "Show Last CID" in `/debug` panel
3. User pastes cid to admin
4. Admin searches logs: `cid=a1b2c3d4`
5. See entire chain: CALLBACK_RECEIVED → CALLBACK_ROUTED → reason_code → next action

---

## Log Format

### JSON (Recommended)

```json
{"ts": "2026-01-13T10:30:45Z", "name": "CALLBACK_ACCEPTED", "cid": "a1b2c3d4", ...}
```

**Advantages**:
- Parseable by Render log search
- Field extraction works
- Easy to import to analytics tools

### ENV Controls

```bash
LOG_FORMAT=json           # or "kv" for key=value
LOG_LEVEL=INFO            # or DEBUG if debug_mode enabled
SILENCE_GUARD=true        # Warn if handler returns without logging result
```

---

## Criteria of Completion (DoD)

✅ **All Met**:

1. **Correlation ID traces entire flow**
   - Single `cid` links 3-6 events
   - Events: RECEIVED → ROUTED → ACCEPTED/REJECTED → ANSWER_CALLBACK

2. **Every rejection has reason_code**
   - `CALLBACK_REJECTED` always has `reason_code` field
   - Reason codes: PASSIVE_REJECT, STATE_MISMATCH, VALIDATION_FAILED, etc.

3. **UI screens & buttons tracked**
   - `screen_id` logged on UI_RENDER
   - `button_id` logged on CALLBACK_RECEIVED
   - UI map (SSOT) validates transitions

4. **Searchable in Render logs**
   - Format: JSON line (one event per line)
   - Search: `cid=a1b2c3d4` finds all events for that action
   - Search: `reason_code=STATE_MISMATCH` finds all rejections by type

5. **/debug command for admin**
   - Shows last 10 events summary
   - Shows last cid (copy-paste to logs)
   - Enables debug logs for 30 min

6. **Smoke test passes**
   - `smoke_buttons_instrumentation.py` verifies chain
   - CI red if events missing
   - Runs on every deploy

---

## Usage Examples

### "User says button doesn't work"

```
Admin: /debug → copy last cid=a1b2c3d4
User: Button "Generate Image" not responding
Admin: Search logs for cid=a1b2c3d4
Logs show:
  CALLBACK_RECEIVED ✅
  CALLBACK_ROUTED ✅
  CALLBACK_REJECTED reason_code=PASSIVE_REJECT
  → Bot in PASSIVE mode (waiting for ACTIVE)
Result: "Another instance is processing, try in 10 seconds"
```

### "Parameters always fail validation"

```
Search logs for reason_code=VALIDATION_FAILED
Find: param_name=aspect_ratio, value="16:10", allowed="16:9, 1:1, 4:3"
Fix: Update UI to show valid options
```

### "Callbacks are slow"

```
Search logs for "DISPATCH_START" and "DISPATCH_OK"
Compare latency_ms for each cid
Identify slow queries by domain (KIE timeout, DB lock, etc.)
```

---

## Next Steps (Future Enhancements)

1. **Metrics Dashboard**: Export logs → analytics (Grafana, Datadog)
2. **Alerting**: Send admin alert if error rate > 5%
3. **Replay**: Reconstruct user session from logs
4. **Model versioning**: Track which model version handled each request

---

## Files

- [app/telemetry/logging_contract.py](../app/telemetry/logging_contract.py) — Core log_event, ReasonCode, EventType
- [app/telemetry/ui_registry.py](../app/telemetry/ui_registry.py) — Screen/button SSOT
- [app/telemetry/telemetry_helpers.py](../app/telemetry/telemetry_helpers.py) — Helper functions
- [app/handlers/debug_handler.py](../app/handlers/debug_handler.py) — /debug command
- [scripts/smoke_buttons_instrumentation.py](../scripts/smoke_buttons_instrumentation.py) — Smoke test

---

**Principle**: If you can't find it in logs within 60 seconds, it's a telemetry bug.
