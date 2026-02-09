# Testing Guide

## Quick Start

### Run All Tests
```bash
python -m pytest tests/ -q
```

### Run Critical Tests Only (fast, ~1s)
```bash
python -m pytest tests/test_critical_flows.py tests/test_mvp_invariants.py -v
```

### Run Bot E2E Smoke
```bash
python -m pytest tests/test_callbacks_smoke.py tests/test_buttons_smoke.py tests/test_e2e_flow.py -v
```

### Run Mini App E2E Smoke
```bash
python -m pytest tests/test_webapp_integration.py -v
```

---

## Test Categories

### Unit Tests
Core business logic without external dependencies.

```bash
python -m pytest tests/test_price_resolver.py tests/test_balance_idempotency.py tests/test_model_input_validation.py -v
```

### Integration Tests
Handlers, DB transactions, idempotency.

```bash
python -m pytest tests/test_mvp_invariants.py tests/test_history_and_storage.py tests/test_payment_idempotency_storage.py -v
```

### Bot E2E Smoke
Simulate Telegram updates/callbacks.

```bash
python -m pytest tests/test_all_scenarios_e2e.py tests/test_input_parameters_wizard_flow.py -v
```

### Mini App E2E Smoke
Web app integration tests.

```bash
python -m pytest tests/test_webapp_integration.py tests/test_healthcheck.py -v
```

---

## Environment Setup

### Required Environment Variables

```bash
# Minimal for tests (most are mocked)
export BOT_TOKEN="test_token"
export BOT_INSTANCE_ID="partner-01"
export KIE_API_KEY="test_key"
export DATABASE_URL="sqlite:///:memory:"  # or your postgres URL
```

### Install Dependencies

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

### Run Tests with Coverage

```bash
python -m pytest tests/ --cov=app --cov-report=html
```

---

## CI Integration

### GitHub Actions (example)

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -q --tb=short
```

---

## Test File Reference

| File | Purpose |
|------|---------|
| `test_critical_flows.py` | Core user journeys |
| `test_mvp_invariants.py` | Balance, isolation, payment invariants |
| `test_balance_idempotency.py` | Debit exactly-once |
| `test_callbacks_smoke.py` | All callbacks don't crash |
| `test_buttons_smoke.py` | Button registry and routing |
| `test_input_parameters_wizard_flow.py` | Parameter input wizard |
| `test_webapp_integration.py` | Mini app API endpoints |
| `test_confirm_generation_20clicks_single_charge.py` | Spam-click protection |

---

## Debugging Failed Tests

### Verbose output
```bash
python -m pytest tests/test_name.py -v --tb=long
```

### Stop on first failure
```bash
python -m pytest tests/ -x
```

### Run specific test
```bash
python -m pytest tests/test_file.py::test_function_name -v
```

### Show print statements
```bash
python -m pytest tests/test_file.py -s
```
