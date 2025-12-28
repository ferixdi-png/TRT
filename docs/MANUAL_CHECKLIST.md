# Manual E2E Checklist (Telegram Bot)

Use this checklist to validate the full user journey via logs (no manual DB edits).

1. **/start**
   - Expect main menu rendered; log should show navigation handler firing.
2. **Open main menu**
   - Buttons visible: popular, formats, free, history, balance, pricing, support.
3. **Select a model**
   - Choose any **free** model (top-5 cheapest auto-configured). Log should include model_id.
4. **Wizard asks required fields**
   - Wizard overview shows required inputs. Logs: `Wizard checklist: start for model <id>`.
5. **User inputs values**
   - Each field prompt appears; skipping optional works. If spec missing, user is returned to menu with an error without crashes.
6. **Generation starts automatically**
   - After last field (or immediately if no fields), log shows generation trigger; message edits to "Запускаю генерацию...".
7. **Result delivered**
   - Generation handler posts result or error message; ensure no duplicate charges and idempotency via processed updates.
8. **Back to menu**
   - User can tap "🏠 В меню" and return to stable menu from any step, including error fallbacks.

For audits, tail webhook logs and confirm all steps are present and no exceptions are raised during the flow.
