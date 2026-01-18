# Placeholders Report

**Runtime placeholders:** 0 (all placeholder modules/docstrings removed; remaining markers are control-flow or interface defaults).

| File | Symbol | Why it exists | Runtime reachable? |
| --- | --- | --- | --- |
| app/services/kie_input_builder.py | `return None`, `pass` | Validation helpers return `None` for invalid inputs and swallow non-critical branches. | Yes |
| app/storage/base.py | `pass` | Abstract interface methods; concrete storages override. | Yes |
| app/storage/json_storage.py | `pass` | No-op hooks when optional storage paths are unused. | Yes |
| app/storage/github_storage.py | `return None` | Optional error-handling paths when storage is unavailable. | Yes |
| app/buttons/registry.py | `return None` | Lookup returns `None` when handler is not found. | Yes |
| app/buttons/fallback.py | `pass` | Defensive fallback when reply attempts fail. | Yes |
| app/helpers/models_menu.py | `return None` | Guard for unresolved callback/model IDs. | Yes |
| app/helpers/models_menu_handlers.py | `pass` | Defensive `query.answer()` failures are ignored. | Yes |
| app/models/registry.py | `pass` | Guarded fallback on missing YAML/API data. | Yes |
| app/observability/error_guard.py | `pass`, `return None` | Error guard fallbacks and optional context resolution. | Yes |
| app/observability/no_silence_guard.py | `pass` | Defensive query.answer() failure handling. | Yes |
| app/services/pricing_service.py | `return None` | Pricing lookup optional paths. | Yes |
| app/utils/healthcheck.py | `pass` | Suppress noisy logs in fallback HTTP handler. | Yes |
| app/utils/retry.py | `pass` | Ignore non-fatal exception in retry loop. | Yes |
| app/telegram_error_handler.py | `pass` | Best-effort error reporting path. | Yes |
| pricing/engine.py | `return None` | Pricing API indicates missing rates without throwing. | Yes |
| scripts/verify_repo_invariants.py | `pass` | Non-runtime script guard for best-effort validation. | No |
| scripts/render_logs.py | `pass`, `return None` | Non-runtime log parsing utilities. | No |
| scripts/render_logs_tail.py | `pass`, `return None` | Non-runtime log tail utilities. | No |
| scripts/full_site_crawler.py | `pass`, `return None` | Non-runtime crawler best-effort handling. | No |
| scripts/sync_kie_models.py | `return None` | Non-runtime sync fallback. | No |
| scripts/check_all_cheap_models.py | `pass` | Non-runtime report builder. | No |
| scripts/scan_env_usage.py | `pass` | Non-runtime scanner. | No |
