# PROJECT STATE (Syntx-mode)

## 1) Build / Env
- Deploy: Render webhook (`main_render.py`), KIE_BASE_URL=https://api.kie.ai
- Required env: TELEGRAM_BOT_TOKEN, KIE_API_KEY; optional: FREE_TIER_MODEL_IDS (defaults to top-5 cheapest)
- Storage: prefers Postgres via DATABASE_URL, falls back to JSON

## 2) Release Gates
- [ ] G1 Foundation — stage logs need audit; progress callbacks awaited; callback persistence wired; reply-once guard added (DB-backed)
- [ ] G2 Free 100% — payload contracts ok; z-image guarded; callback parser handles resultUrl/resultUrls; poll/callback history verification + reply-once e2e pending
- [ ] G3 Payments — TEST_MODE default off; regression ensures paid flows don't skip billing when env unset
- [ ] G4 Buttons — map below, coverage incomplete
- [ ] G5 Referral — present in codebase, needs validation/logging
- [ ] G6 All-model dynamic UI — text2image optional fields now exposed from schema (aspect_ratio/num_images/seed), needs full model sweep
- [ ] G7 History — callback persistence added; history UI still needs success/fail verification

## 3) FREE TOP-5 status matrix
| Model | payload ok? | wizard ok? | createTask ok? | poll/callback ok? | media send ok? | history ok? |
|-------|-------------|------------|----------------|-------------------|----------------|-------------|
| z-image | ✅ contract tests (adds default aspect_ratio + no-overlay guard) | ✅ wizard fallback injects aspect_ratio even without overlay | ✅ aspect_ratio auto-filled even when empty | ☐ (progress awaited; callback persistence wired; reply-once guard added) | ☐ | ☐ |
| recraft/remove-background | ✅ contract tests (image+image_url mirrored) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| infinitalk/from-audio | ✅ contract+schema overlay | ☐ | ☐ | ☐ | ☐ | ☐ |
| google/imagen4-fast | ✅ contract tests | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| google/imagen4 | ✅ contract tests (payload wrap) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |

## 4) ALL MODELS matrix (sample rows; expand each iteration)
| Model | in_UI? | wizard_schema_ok? | required_inputs_ok? | optional_inputs_supported? | payload_ok? | generation_verified? | history_ok? |
|-------|--------|-------------------|--------------------|---------------------------|-------------|---------------------|-------------|
| google/imagen4-fast | ✅ | ✅ (schema-based) | ✅ | ✅ (aspect_ratio/num_images/seed/negative_prompt exposed) | ✅ | ☐ | ☐ |
| infinitalk/from-audio | ✅ | ✅ (overlay schema) | ✅ (image_url/audio_url/prompt) | ✅ (resolution enum, seed number) | ✅ | ☐ | ☐ |
| recraft/remove-background | ✅ | ✅ | ✅ (image/image_url mirrored) | ✅ (prompt optional) | ✅ | ☐ | ☐ |

## 5) PAID models status matrix
- Not audited this iteration (blocked until FREE is green).

## 6) UI Buttons map
- /start → main menu (model selection) — value: entrypoint; needs log trace check
- “История” → history handler — value: recall past jobs; needs success/fail coverage
- “Поддержка” → support text — value: user help; trace not audited
- “Пригласить друга” → referral info — value: bonuses; needs reward logging check
- “Подтвердить” (confirm_cb) → generation start — value: launches paid/free pipeline; now defaults to production (TEST_MODE off by default); covered by regression for paid flow default

## 7) Known issues
- Free models beyond z-image/google not exercised end-to-end; callback persistence only wired, needs history verification.
- Stage logging coverage for request_id/payload_hash needs inspection.
- Optional fields for text2image models were hidden; now exposed, but UI flow per-model still needs audit (advanced settings UX).
- z-image aspect_ratio default injected even when overlay missing; need poll/history validation to mark path green.

## 8) Next iteration plan
- Persist callback outcomes into history records (succeeded/failed) and prove reply-once covers poll-first vs callback-first flows end-to-end.
- Audit stage logs for request_id/payload_hash through create_task→reply; add proof in tests/logs.
- Extend mini-e2e to cover infinitalk/from-audio (image_url+audio_url+prompt required) and start marking poll/callback matrix cells.
