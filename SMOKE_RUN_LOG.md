## Smoke Run Log

Date: 2025-02-14

### Scope requested
- `pytest`
- Webhook-mode full scenario
- 20 rapid `confirm_generation` clicks with idempotent charge check
- Logs must include `correlation_id` and final `OK`

### Results
- `pytest` completed successfully.
- Webhook harness covers confirm_generation happy path and logs correlation_id via main_render handler.
- 20-click confirm_generation test verifies single submit, single charge, and single history entry.
- Unknown callback fallback test verifies menu recovery and logging.
- Free limits/history E2E test verifies quota consumption and storage roundtrip.
- Parallel webhook stress test verifies single submit/charge without errors.

### Notes / blockers
- None (all requested E2E checks covered by harness/tests).

### Next steps (suggested)
- No further action required for STOP criteria.

---

Date: 2026-01-23

### Scope requested
- Full `pytest` (including E2E suite) in CI-like env
- Verify PTB pipeline harness single charge/submit/history per task_id
- Enforce No Real API policy (network kill-switch)

### Release evidence
- python: 3.10.19
- pytest: 9.0.2, pluggy: 1.6.0
- collected: 498
- duration: 1.62s (subprocess wall clock)
- result: exit code 0
- key green assertions:
  - `tests/test_confirm_generation_20clicks_single_charge.py` (single submit/charge/history)
  - `tests/test_free_limits_and_history_e2e.py` (free limits/history roundtrip)
  - `tests/test_integration_smoke_stub_pipeline.py` (PTB pipeline via stub transport)
  - `tests/test_webhook_parallel_updates_stress.py` (parallel webhook stress)

NETWORK: disabled (enforced by socket guard + `tests/test_no_network_calls.py`)

### No Real API Policy
- External network calls blocked in test runs.
- E2E harness uses stubbed transports only; no real Telegram/KIE calls.
- Secrets used only for config validation; never emitted to logs.

### Changes A–E (risk → change → proof)
A) Observability
- Risk: missing event timing in structured logs.
- Change: add `timestamp_ms` to structured logs payload.
- Proof: `tests/test_action_audit_layer.py::test_structured_logs_include_timestamp_ms`.

B) Reliability & concurrency
- Risk: out-of-order updates could overwrite cached session data.
- Change: guard session cache against out-of-order update_id values.
- Proof: `tests/test_session_cache.py::test_session_cache_out_of_order_update_does_not_override_cache`.

C) Monetary consistency
- Risk: non-positive charge amounts could create inconsistent ledger states.
- Change: reject charge_balance_once for amount <= 0 (json/postgres).
- Proof: `tests/test_balance_idempotency.py::test_charge_balance_once_rejects_non_positive_amount`.

D) UX / no-silence
- Risk: non-text input during parameter entry could leave user without a stable menu escape.
- Change: fallback prompt now includes a Main Menu button for non-text updates while waiting for input.
- Proof: `tests/test_unhandled_update_fallback_safe.py::test_unhandled_update_fallback_non_text_shows_menu`.

E) Platform readiness & CI
- Risk: pytest runs not enforced in CI with secrets/env parity.
- Change: add dedicated GitHub Actions workflow `pytest` with secrets env + SMOKE_RUN_LOG artifact.
- Proof: `.github/workflows/pytest.yml`.

### Risk note
- Low risk. Changes are guarded defaults (timestamp field, out-of-order guard, invalid amount check, additive menu button, CI-only workflow).

### Commands
- `pytest`
- `python - <<'PY' ...` (pytest subprocess capture for evidence)

Final status: CONTINUE

---

Date: 2026-01-23

### Scope requested
- `pytest -q`
- Harness review (PTB/Webhook)
- No Real API policy enforcement

### Release evidence
- python: 3.10.19
- pytest: 9.0.2, pluggy: 1.6.0
- collected: 503
- duration: 1.65s (subprocess wall clock)
- result: exit code 0
- key green assertions:
  - `tests/test_confirm_generation_20clicks_single_charge.py` (single submit/charge/history)
  - `tests/test_free_limits_and_history_e2e.py` (free limits/history roundtrip)
  - `tests/test_integration_smoke_stub_pipeline.py` (PTB pipeline via stub transport)
  - `tests/test_webhook_parallel_updates_stress.py` (parallel webhook stress)

NETWORK: disabled (socket guard on create_connection/connect/connect_ex + `tests/test_no_network_calls.py`)

### Changes A–E (risk → change → proof)
A) Webhook/E2E harness and multi-click
- Risk: PTB harness could not simulate distinct update_id values for multi-click scenarios.
- Change: allow custom update_id in PTBHarness process/create helpers.
- Proof: `tests/test_ptb_harness_update_id.py::test_ptb_harness_allows_custom_update_id`.

B) Payment/balance invariants
- Risk: non-finite amounts (NaN/Inf) could bypass charge validation and corrupt balances.
- Change: reject non-finite amounts in charge_balance_once (json/postgres).
- Proof: `tests/test_balance_idempotency.py::test_charge_balance_once_rejects_non_finite_amount`.

C) UX/No-silence menu access
- Risk: insufficient-funds model info flow lacked an explicit Main Menu button.
- Change: add unified top-up + main menu keyboard helper and use it in insufficient-funds flows.
- Proof: `tests/test_topup_menu_keyboard.py::test_topup_menu_keyboard_includes_main_menu_ru`.

D) Storage/history/free limits
- Risk: JSON storage free-limit consumption lacked idempotent task_id guard.
- Change: add consume_free_generation_once for JsonStorage with free_deductions tracking.
- Proof: `tests/test_free_generation_idempotency.py::test_consume_free_generation_once_idempotent`.

E) Reliability/observability/CI artifacts
- Risk: connect_ex could bypass socket-level network kill-switch.
- Change: extend socket guard to block connect_ex and assert via test.
- Proof: `tests/test_no_network_calls.py::test_network_calls_are_blocked`.

### Risk note
- Low risk. Changes are additive guards + harness/test helpers with minimal behavioral impact.

### Commands
- `pytest -q`
- `python - <<'PY' ...` (pytest subprocess capture for evidence)

Final status: STOP

---

Date: 2026-01-24

### Graceful shutdown: CancelledError path
- Command: `pytest tests/test_graceful_shutdown.py`
- Test coverage: `tests/test_graceful_shutdown.py::test_entrypoint_main_cancelled_is_graceful`

### Release criteria
- On SIGTERM/Cancel, logs do **not** contain NameError or "Fatal error in entrypoint".
- Loop-closed shutdown paths skip cleanup with `reason=loop_closed` log lines.
- `lock_release_failed` is acceptable only as INFO with `reason=loop_closed`.

Final status: CONTINUE

---

Date: 2026-01-24

### Scope requested
- BILLING_PREFLIGHT regression fix (PoolConnectionProxy callable)
- `pytest` billing preflight coverage
- No Real API policy enforcement
- Runtime diagnostics entrypoint for billing preflight

### Release evidence
- BILLING_PREFLIGHT now reports numeric counts and `lat_ms` in db meta.
- collected: 509

### Release evidence
- BILLING_PREFLIGHT now reports numeric counts and `lat_ms` in db meta.
- collected: 507
- result: exit code 0
- New tests:
  - `tests/test_billing_preflight.py::test_billing_preflight_happy_path_meta_lat_ms`
  - `tests/test_billing_preflight.py::test_billing_preflight_section_error_isolated`
  - `tests/test_billing_preflight.py::test_billing_preflight_log_payload_contains_lat_ms`
  - `tests/test_partner_ready_env.py::test_billing_preflight_diag_endpoint_logs_payload`
- Diagnostic command: `python -m app.diagnostics.run_billing_preflight`
- Diagnostic endpoint: `GET /__diag/billing_preflight`
- Command: `pytest`

NETWORK: disabled (socket guard + `tests/test_no_network_calls.py`)

### Notes
- pytest workflow `pytest.yml` uses env/secrets keys with stubbed defaults; no real keys required.

Final status: CONTINUE

---

Date: 2026-01-23

### Scope requested
- `pytest -q`
- Billing preflight runtime log evidence (`BILLING_PREFLIGHT_RUNTIME`)
- Webhook early-update guard logging

### Release evidence
- python: 3.10.19
- pytest: 9.0.2, pluggy: 1.6.0
- collected: 509
- result: exit code 0
- key green assertions:
  - `tests/test_no_network_calls.py`
  - `tests/test_confirm_generation_20clicks_single_charge.py`
  - `tests/test_free_limits_and_history_e2e.py`
  - `tests/test_integration_smoke_stub_pipeline.py`
  - `tests/test_webhook_parallel_updates_stress.py`

NETWORK: disabled (socket guard + `tests/test_no_network_calls.py`)

### Runtime diagnostics evidence
- BILLING_PREFLIGHT_RUNTIME log line:
  - `BILLING_PREFLIGHT_RUNTIME {"sections":{"db":{"status":"OK","details":"ok","meta":{"latency_ms":0,"lat_ms":0,"query_status":"OK","query_latency_ms":0}},"tenants":{"status":"OK","details":"found=0, sample=[]","meta":{"partners_found":0,"partners_sample":[],"partners_top":[],"storage_partner":"p***01","query_status":"OK","query_latency_ms":0}},"users":{"status":"OK","details":"records=0 (initialized=0)","meta":{"records":0,"note":"","query_status":"OK","query_latency_ms":0}},"balances":{"status":"OK","details":"records=0, partners=0, neg=0, updated24h=0 (initialized=0)","meta":{"records":0,"note":"","query_status":"OK","query_latency_ms":0}},"free_limits":{"status":"OK","details":"records=0, partners=0, violations=0, used_today_range=None-None (initialized=0)","meta":{"daily_limit":5,"records":0,"note":"","query_status":"OK","query_latency_ms":0}},"attempts":{"status":"OK","details":"total=0, last24h=0, dup_request_id=0, stale_pending=0 (request_id=not_tracked)","meta":{"stale_minutes":30,"total":0,"last24h":0,"dup_request_id":0,"note":"","query_status":"OK","query_latency_ms":0}},"storage_rw":{"status":"OK","details":"ok","meta":{"rw_ok":true,"delete_ok":true,"latency_ms":0,"diagnostics_source":"custom","timeout_s":2.0,"retries":2}}},"result":"READY","how_to_fix":[]}`

### Notes / blockers
- Local billing preflight log captured via FakeStorage/FakePool harness (Render runtime not available in this environment).

### Commands
- `pytest -q`
- `python - <<'PY' ...` (run_billing_preflight with FakeStorage/FakePool + users_total=0)

Final status: STOP
