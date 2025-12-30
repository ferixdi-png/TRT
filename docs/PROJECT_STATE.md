# PROJECT STATE (Syntx-mode)

## 1) Build / Env
- Deploy: Render webhook (`main_render.py`), KIE_BASE_URL=https://api.kie.ai
- Required env: TELEGRAM_BOT_TOKEN, KIE_API_KEY; optional: FREE_TIER_MODEL_IDS (defaults to top-5 cheapest)
- Storage: auto (prefers Postgres via DATABASE_URL, falls back to JSON)

## 2) Release Gates
- [ ] G1 Foundation (CI green, stage logs) — tests partial, stage logs need audit
- [ ] G2 Free 100% — payload contracts in progress; z-image now hard-guards aspect_ratio even without overlay; callback parser normalizes singular resultUrl
- [ ] G3 Payments — default TEST_MODE forced to off; regression ensures paid flows don't skip billing when env unset
- [ ] G4 Buttons — map below, coverage incomplete
- [ ] G5 Referral — present in codebase, needs validation/logging

## 3) FREE TOP-5 status matrix
| Model | payload ok? | wizard ok? | createTask ok? | poll/callback ok? | media send ok? | history ok? |
|-------|-------------|------------|----------------|-------------------|----------------|-------------|
| z-image | ✅ contract tests (adds default aspect_ratio + no-overlay guard) | ✅ wizard fallback injects aspect_ratio even without overlay | ☐ | ☐ | ☐ | ☐ |
| recraft/remove-background | ✅ contract tests (image+image_url mirrored) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| infinitalk/from-audio | ✅ contract+schema overlay | ☐ | ☐ | ☐ | ☐ | ☐ |
| google/imagen4-fast | ✅ contract tests | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| google/imagen4 | ✅ contract tests (payload wrap) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |

## 4) PAID models status matrix
- Not audited this iteration (blocked until FREE is green).

## 5) UI Buttons map
- /start → main menu (model selection) — value: entrypoint; needs log trace check
- “История” → history handler — value: recall past jobs; needs success/fail coverage
- “Поддержка” → support text — value: user help; trace not audited
- “Пригласить друга” → referral info — value: bonuses; needs reward logging check
- “Подтвердить” (confirm_cb) → generation start — value: launches paid/free pipeline; now defaults to production (TEST_MODE off by default); covered by regression for paid flow default

## 6) Known issues
- Free models beyond z-image/google not exercised end-to-end; callbacks/persistence unverified.
- Stage logging coverage for request_id/payload_hash needs inspection.
- Legacy PROJECT_STATE at repo root is outdated; use this file going forward.
- z-image aspect_ratio default now injected even when overlay missing (wizard also injects fallback); need createTask/poll validation to mark path green.

## 7) Next iteration plan
- Verify poll/callback parsing stores history for one free model; now parser covers resultUrl/resultUrls.
- Audit stage logs for request_id/payload_hash through create_task→reply.
- Extend mini-e2e to cover infinitalk/from-audio now that schema matches free-tier contract (image_url+audio_url+prompt required).
- Add UI button map tests/logs for history/referral to move G4 forward.
