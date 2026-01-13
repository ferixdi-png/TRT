# Git Workflow & Development Process

## Branch Strategy

**Single branch**: `main` (production)

- All commits go directly to `main`
- Render auto-deploys on push to `main`
- No feature branches (small team, fast iteration)

## Commit Standards

### Format
```
<type>: <short summary> (<issue/ticket if any>)

<optional detailed description>

PROOF:
- ✅ <verification step 1>
- ✅ <verification step 2>
- ✅ <verification step 3>
```

### Types
- `fix`: Bug fix (production issue)
- `feat`: New feature
- `refactor`: Code restructuring (no behavior change)
- `docs`: Documentation only
- `chore`: Build process, dependencies
- `test`: Add/fix tests
- `perf`: Performance improvement

### Examples

**Good commit**:
```
fix: Prevent Decimal serialization in /health

Changed balance field to float() before JSON serialization.
Resolves P0 "Object of type Decimal is not JSON serializable" error.

PROOF:
- ✅ /health returns 200 OK with valid JSON
- ✅ smoke_test.py S0 PASS
- ✅ No Decimal-related errors in logs (checked last 100 lines)
```

**Bad commit**:
```
wip
```

## Pre-Commit Checklist

Before `git commit`:

1. ✅ Run `python scripts/verify.py` → must PASS
2. ✅ Run `python scripts/smoke.py` → must PASS (if server running)
3. ✅ No syntax errors: `python -m py_compile <changed files>`
4. ✅ No forbidden patterns: Check against `product/truth.yaml` → `observability.forbidden_log_patterns`
5. ✅ Type hints added (for new functions)
6. ✅ Docstrings updated (for new modules/classes)

## Deployment Flow

```
Local Dev → Git Commit → Push to main → CI (Truth Gate) → Render Deploy → Smoke Tests
```

### Step-by-Step

1. **Make changes locally** (in dev container or local machine)
2. **Test locally**:
   ```bash
   python main_render.py  # Start server
   curl http://localhost:8080/health  # Check /health
   ```
3. **Run gates**:
   ```bash
   python scripts/verify.py  # Architecture validation
   python scripts/smoke.py --url http://localhost:8080  # Smoke tests
   ```
4. **Commit with PROOF**:
   ```bash
   git add <files>
   git commit -m "fix: <summary>

   PROOF:
   - ✅ verify.py PASS
   - ✅ smoke.py S0-S2 PASS
   - ✅ Manual test: /start → works"
   ```
5. **Push to main**:
   ```bash
   git push origin main
   ```
6. **Monitor CI**: Check GitHub Actions → Truth Gate job
7. **Monitor Render**:
   - Render Dashboard → Deployments
   - Wait for "Live" status (~3-5 minutes)
8. **Validate production**:
   ```bash
   curl https://<app-name>.onrender.com/health
   python scripts/smoke.py --url https://<app-name>.onrender.com
   ```
9. **Check bot**: Send `/start` to Telegram bot
10. **Monitor logs**: Render Dashboard → Logs (watch for 10 minutes)

## Rollback

If deployment breaks production:

1. **Immediate**: Render Dashboard → Deployments → Rollback to previous
2. **Fix forward**: `git revert <bad-commit>` + push (preferred if issue is minor)
3. **Force rollback**: 
   ```bash
   git reset --hard <last-good-commit>
   git push --force origin main
   ```
   ⚠️ **Dangerous**: Only use if deploy is completely broken

## Hotfix Process

For critical production bugs:

1. **Fix locally** (minimal change)
2. **Test fix**:
   ```bash
   python scripts/verify.py
   # Manual test of the specific bug scenario
   ```
3. **Commit with `fix:` prefix**:
   ```bash
   git commit -m "fix(P0): <critical bug description>"
   ```
4. **Push immediately**: `git push origin main`
5. **Monitor deployment closely** (stay available for 30 minutes)
6. **Verify fix in production**: Test the exact bug scenario

## Tagging Releases

After successful deployment + validation:

```bash
git tag -a v2.0.1 -m "Stable release: <summary of changes>"
git push origin v2.0.1
```

**Tag format**: `vMAJOR.MINOR.PATCH`
- MAJOR: Breaking changes (e.g., v1 → v2)
- MINOR: New features (e.g., v2.0 → v2.1)
- PATCH: Bug fixes (e.g., v2.0.0 → v2.0.1)

## Definition of "Stable"

A commit is tagged "stable" after:

1. ✅ Deployed to Render
2. ✅ `/health` returns 200 OK
3. ✅ Bot responds to `/start`
4. ✅ No errors in logs for 10+ minutes
5. ✅ Manual smoke test (generate image if ACTIVE mode)

## Working with quarantine/

Files in `quarantine/` are:
- Not imported by blessed path (`main_render.py`)
- Not part of CI gates
- Kept for historical reference or migration

**Rules**:
- ❌ Never import from `quarantine/` in production code
- ✅ Can be deleted if > 6 months old
- ✅ Can be moved back to main codebase if needed (after validation)

## Knowledge Base Updates

When changing architecture:

1. Update `product/truth.yaml` (single source of truth)
2. Update relevant `kb/*.md` files (e.g., `kb/architecture.md` if flow changes)
3. Run `python scripts/verify.py` to check contract compliance
4. Commit both code + docs in same commit (keep in sync)

**Example**:
```bash
# Changed database schema
git add migrations/003_add_user_preferences.sql
git add kb/database.md  # Updated schema docs
git add product/truth.yaml  # Updated database section
git commit -m "feat: Add user preferences table

PROOF:
- ✅ Migration tested locally
- ✅ kb/database.md updated with new schema
- ✅ product/truth.yaml updated"
```

## Debugging Production Issues

1. **Check Render logs**: Dashboard → Logs → Search for error
2. **Check /health**: `curl https://<app-name>.onrender.com/health`
3. **Check lock state**: Look for `lock_state` in /health response
4. **Reproduce locally**:
   ```bash
   export DATABASE_URL=<local postgres>
   python main_render.py
   # Trigger the issue
   ```
5. **Fix + deploy** (see Hotfix Process above)

## CI/CD Pipeline

`.github/workflows/truth_gate.yml`:

1. **Validate YAML**: `product/truth.yaml` syntax check
2. **Verify architecture**: `scripts/verify.py` (checks invariants)
3. **Smoke tests**: `scripts/smoke.py` (basic health checks)
4. **Forbidden patterns**: Grep for wildcard imports, deprecated APIs

If any step fails → deployment BLOCKED.

## Development Loop (Typical Day)

```
1. Pull latest: git pull origin main
2. Make changes (code + tests)
3. Test locally: python main_render.py
4. Run gates: python scripts/verify.py && python scripts/smoke.py
5. Commit with PROOF
6. Push to main
7. Monitor deployment
8. Tag as stable (if all green)
9. Repeat
```
