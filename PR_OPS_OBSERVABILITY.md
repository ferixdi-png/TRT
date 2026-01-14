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

- [x] Code changes complete (A-F all tasks)
- [x] Tests added (config loader + smoke tests)
- [x] Makefile targets added (ops-*)
- [x] .gitignore updated (artifacts/)
- [x] TRT_REPORT.md updated (repo + Desktop)
- [x] Admin command added (`/admin_ops_snapshot`)
- [x] Branch pushed to GitHub
- [x] All commits pushed
- [ ] PR created (use link: https://github.com/ferixdi-png/TRT/pull/new/feat/ops-observability-loop)
- [ ] Smoke tests pass (run `make ops-all` after setting up TRT_RENDER.env)
- [ ] Ready for review

## Next Steps

1. Create PR using GitHub link above
2. Set up Desktop `TRT_RENDER.env` with credentials
3. Run `make ops-all` to verify
4. Test admin command: `/admin_ops_snapshot` (admin only)
5. Review critical5.md output for accuracy

