# PR: Ops Observability Loop

## Summary

Adds automated observability loop: Render logs fetching + DB read-only diagnostics + critical issue detection.

## Changes

### New Modules

- `app/ops/observer_config.py` - Config loader from Desktop `TRT_RENDER.env` or env vars
- `app/ops/render_logs.py` - Render logs fetcher (read-only, sanitized)
- `app/ops/db_diag.py` - DB read-only diagnostics
- `app/ops/critical5.py` - Critical issue detector (top-5 ranked by score)

### Makefile Targets

- `make ops-fetch-logs` - Fetch Render logs (last 60 minutes)
- `make ops-db-diag` - Run DB diagnostics
- `make ops-critical5` - Detect top-5 critical issues
- `make ops-all` - Run all ops checks

### Tests

- `tests/test_ops_config.py` - Unit tests for config loader

### Configuration

Requires Desktop `TRT_RENDER.env` file with:
```
RENDER_API_KEY=...
RENDER_SERVICE_ID=...
DATABASE_URL_READONLY=...
```

Or set via environment variables (priority: env > file).

## Safety

- ✅ All operations are read-only (no writes to production)
- ✅ Secrets redacted in logs and outputs
- ✅ Graceful degradation if config missing
- ✅ No changes to production bot code
- ✅ All outputs in `artifacts/` (gitignored)

## How to Run

```bash
# Run all ops checks
make ops-all

# Or individually
make ops-fetch-logs
make ops-db-diag
make ops-critical5
```

## Outputs

- `artifacts/render_logs_latest.txt` - Sanitized Render logs
- `artifacts/db_diag_latest.json` - DB diagnostics (JSON)
- `artifacts/critical5.md` - Top-5 critical issues (Markdown)

## Validation

- ✅ Unit tests pass
- ✅ Syntax check passes
- ✅ No production code changes
- ✅ All outputs gitignored

## Checklist

- [x] Code changes complete
- [x] Tests added
- [x] Makefile targets added
- [x] .gitignore updated
- [x] TRT_REPORT.md updated (repo + Desktop)
- [x] Branch pushed to GitHub
- [ ] PR created (use link from git push output)
- [ ] Smoke tests pass
- [ ] Ready for review

