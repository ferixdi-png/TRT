# PROJECT STATE (Syntx-mode)

## 1) Build / Env
- Deploy: Render webhook (`main_render.py`), KIE_BASE_URL=https://api.kie.ai
- Required env: TELEGRAM_BOT_TOKEN, KIE_API_KEY; optional: FREE_TIER_MODEL_IDS (defaults to top-5 cheapest)


## 3) FREE TOP-5 status matrix
| Model | payload ok? | wizard ok? | createTask ok? | poll/callback ok? | media send ok? | history ok? |
|-------|-------------|------------|----------------|-------------------|----------------|-------------|

| recraft/remove-background | ✅ contract tests (image+image_url mirrored) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| infinitalk/from-audio | ✅ contract+schema overlay | ☐ | ☐ | ☐ | ☐ | ☐ |
| google/imagen4-fast | ✅ contract tests | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |
| google/imagen4 | ✅ contract tests (payload wrap) | ✅ mini-e2e confirm | ☐ | ☐ | ☐ | ☐ |


- “Поддержка” → support text — value: user help; trace not audited
- “Пригласить друга” → referral info — value: bonuses; needs reward logging check
- “Подтвердить” (confirm_cb) → generation start — value: launches paid/free pipeline; now defaults to production (TEST_MODE off by default); covered by regression for paid flow default


