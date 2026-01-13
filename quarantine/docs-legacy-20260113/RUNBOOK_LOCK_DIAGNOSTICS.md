# 🔍 LOCK CONTROLLER DIAGNOSTICS RUNBOOK

## Overview

После рефакторинга (commit 05d5cdb) используется **единственный** `SingletonLockController` для управления состоянием PASSIVE/ACTIVE и минимизации спама пользователям.

## Normal Production Logs Pattern

### ✅ HEALTHY DEPLOYMENT (overlap scenario)

```
[LOCK_CONTROLLER] instance=abc123 watcher=def456
[LOCK_CONTROLLER] PASSIVE MODE (background watcher started)
[LOCK_CONTROLLER] Lock not available (another instance active) | attempt=1
[STATE_SYNC] Passive mode active

... (10s later) ...
[LOCK_CONTROLLER] Lock not available (another instance active) | attempt=2
[PASSIVE MODE] Sent 'updating' to chat_id=12345 (throttled: first notice)

... (15s later) ...
[LOCK_CONTROLLER] Lock not available (another instance active) | attempt=3
[PASSIVE MODE] Throttled notice for chat_id=12345 (last sent 25s ago)

... (22.5s later) ...
[LOCK_CONTROLLER] ✅ Lock acquired | attempt=5
[LOCK_CONTROLLER] PASSIVE → ACTIVE
[STATE_SYNC] ✅ PASSIVE → ACTIVE (lock acquired)
[ACTIVE] Initializing database service...
[ACTIVE] All services initialized

... (from this point forward) ...
[WEBHOOK] Processing update chat_id=12345 (ACTIVE mode)
NO MORE PASSIVE NOTICES SHOULD APPEAR
```

### Key Indicators:
1. **Single watcher**: Only ONE "instance=..." log at startup
2. **One transition**: Exactly ONE "PASSIVE → ACTIVE" log
3. **Throttling works**: "Throttled notice" appears when user sends >1 message
4. **No passive after active**: Zero "[PASSIVE MODE]" logs after transition
5. **Exponential backoff**: Delays increase (10s, 15s, 22.5s, 33.75s, cap at 60s)

---

## Abnormal Patterns (REGRESSION)

### 🚨 MULTIPLE WATCHERS (race condition)

```
[LOCK_CONTROLLER] instance=abc123 watcher=def456
[LOCK_CONTROLLER] PASSIVE MODE (background watcher started)
[LOCK_CONTROLLER] instance=abc123 watcher=xyz789  ← DUPLICATE!
[LOCK_CONTROLLER] PASSIVE MODE (background watcher started)  ← DUPLICATE!
```

**Diagnosis**: Multiple `controller.start()` calls or duplicate `asyncio.create_task(state_sync_loop())`

**Fix**:
- Check background_initialization for duplicate controller creation
- Verify only ONE `state_sync_loop()` task started
- Search codebase: `git grep "controller.start()"`

---

### 🚨 PASSIVE LOGS AFTER ACTIVE

```
[LOCK_CONTROLLER] PASSIVE → ACTIVE
[STATE_SYNC] ✅ PASSIVE → ACTIVE (lock acquired)
... (time passes) ...
[PASSIVE MODE] Sent 'updating' to chat_id=12345  ← SHOULD NOT HAPPEN!
```

**Diagnosis**: 
- `active_state.active` not syncing with controller
- Webhook handler checking stale `active_state.active` instead of `controller.should_process_updates()`

**Fix**:
- Verify state_sync_loop running: `grep "STATE_SYNC" logs`
- Check webhook logic uses `hasattr(active_state, 'lock_controller')` and calls `send_passive_notice_if_needed()`
- Add debug log: `logger.debug(f"[WEBHOOK] active={active_state.active} controller={controller.should_process_updates()}")`

---

### 🚨 USER SPAM (throttling broken)

```
[PASSIVE MODE] Sent 'updating' to chat_id=12345
[PASSIVE MODE] Sent 'updating' to chat_id=12345  ← 5s later (should be throttled!)
[PASSIVE MODE] Sent 'updating' to chat_id=12345  ← 10s later (should be throttled!)
```

**Diagnosis**: 
- Controller throttling bypassed (webhook sending directly)
- Multiple controller instances (each tracks last_user_notice_at separately)

**Fix**:
- Verify webhook calls `controller.send_passive_notice_if_needed(chat_id)` NOT direct `bot.send_message()`
- Check only ONE controller created: `grep "lock_controller = " main_render.py`
- Validate controller state: `print(controller.state.last_user_notice_at)`

---

### 🚨 DUPLICATE "NOT acquired after 60s" WARNINGS

```
[LOCK_CONTROLLER] Lock not available | attempt=6
[LOCK_CONTROLLER] ⚠️ Lock NOT acquired after 60s (retry continues)
[LOCK_CONTROLLER] Lock not available | attempt=7
[LOCK_CONTROLLER] ⚠️ Lock NOT acquired after 60s (retry continues)  ← DUPLICATE!
```

**Diagnosis**: Multiple watcher loops running in parallel

**Fix**:
- Check for duplicate `_watcher_loop()` tasks
- Verify old code removed: `git grep "lock_watcher\|start_background_lock_retry"`
- Should return ZERO matches (both removed in 05d5cdb)

---

## Debugging Commands

### Check for duplicate lock acquisition code
```bash
git grep -n "lock.acquire" | grep -v "controller.py" | grep -v "def acquire"
# Expected output: EMPTY (only controller.py should call lock.acquire)
```

### Check for old retry logic
```bash
git grep -n "lock_watcher\|start_background_lock_retry"
# Expected output: EMPTY (removed in refactor)
```

### Validate single controller instantiation
```bash
git grep -n "SingletonLockController(" main_render.py
# Expected output: Exactly ONE match in background_initialization
```

### Count watcher logs in production (via gh CLI)
```bash
gh api repos/ferixdi-png/TRT/actions/runs --jq '.workflow_runs[0].id' | \
  xargs -I {} gh api repos/ferixdi-png/TRT/actions/runs/{}/logs | \
  grep -c "background watcher started"
# Expected: 1 (single watcher per instance)
```

---

## Performance Metrics

### Throttling Effectiveness
- **Target**: Max 1 "updating" message per user per 60 seconds
- **Measurement**: Count "[PASSIVE MODE] Sent 'updating'" logs for same chat_id
  ```bash
  grep "Sent 'updating' to chat_id=" logs.txt | \
    awk '{print $NF}' | sort | uniq -c | sort -rn
  # Output should show gaps of ≥60s between same chat_id
  ```

### State Transition Latency
- **Target**: <1 second from controller ACTIVE to state_sync update
- **Measurement**: Time delta between logs
  ```bash
  grep -E "LOCK_CONTROLLER.*PASSIVE → ACTIVE|STATE_SYNC.*PASSIVE → ACTIVE" logs.txt
  # Should appear within same second
  ```

---

## Rollback Procedure (if needed)

If production shows regression after 05d5cdb:

```bash
# Revert to previous stable commit
git revert 05d5cdb
git push origin main

# Monitor Render logs for:
# - No more "[LOCK_CONTROLLER]" logs (reverted)
# - Old "[LOCK] Acquired after retry" pattern returns
# - Expect spam issues to resume (known limitation of old code)
```

**Note**: Rollback only if NEW bugs appear. Old issues (spam, duplicate attempts) are expected in pre-refactor code.

---

## Contact & Escalation

**Author**: GitHub Copilot  
**Commit**: 05d5cdb (2024-01-XX)  
**References**:
- [app/locking/controller.py](app/locking/controller.py) - Single lock controller implementation
- [main_render.py](main_render.py) - Refactored startup/webhook logic
- [AUTOPILOT_409_FIX_COMPLETE.md](AUTOPILOT_409_FIX_COMPLETE.md) - Original diagnosis

**Production Validation Checklist**:
- [ ] Single "instance=..." log per deploy
- [ ] One "PASSIVE → ACTIVE" transition
- [ ] Zero passive logs after active
- [ ] Max 1 "updating" per user per 60s
- [ ] Clean continuous operation (no zombie tasks)
