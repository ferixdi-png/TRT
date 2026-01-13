# 🚀 Оставшиеся задачи для D1–D11 PASS

## ✅ Выполнено

- [x] D1–D3: `make verify`, `compileall`, `verify_project.py` проходят
- [x] D4: Health check `/health` возвращает 200
- [x] D5–D6: Callback integration (real URL, endpoint, token validation)
- [x] D7: 402 handling (honest failure, no mock success)
- [x] D8: `.env.test` обновлен (KIE_CALLBACK_PATH/TOKEN, valid bot token)
- [x] D9: Syntax fix в `app/storage/base.py`

## 🔄 В процессе

- [ ] D14: Full `make verify` PASS (ожидаем завершения smoke-тестов)

## ⏳ TODO

### D10: Payment idempotence & atomicity
- [ ] Audit `add_payment()` + `reserve_balance_for_generation()` на race conditions
- [ ] Добавить тест на дублированный платеж с одинаковым `idempotency_key`
- [ ] Проверить atomic commit/rollback в PG storage

### D11: Webhook strict token validation
- [ ] Audit всех webhook endpoints:
  - `/webhook/{secret_path}` (Telegram) – проверить strict token check
  - `/{kie_callback_path}` (KIE) – проверить `X-Callback-Token` validation
- [ ] Убедиться, что при несовпадении токена возвращается 401/403, а не 200

### D12: Menu/handlers consistency
- [ ] Проверить соответствие всех callback_data из `build_model_keyboard()` зарегистрированным handlers
- [ ] Smoke-тест на все кнопки меню (отправка каждого callback_data и проверка ответа)
- [ ] Убедиться, что нет orphan handlers (зарегистрированы, но не используются)

### D13: Docs & Security & Devcontainer
- [ ] README quickstart:
  - Добавить инструкцию по `.env.test` (`cp .env.example .env.test`, затем `source .env.test`)
  - Описать `make verify` workflow
- [ ] TRT_REPORT.md update:
  - Добавить раздел про KIE callback integration
  - Описать 402 handling changes (honest failure)
  - Обновить deployment checklist
- [ ] Security audit:
  - `grep -rn "eval\|exec\|__import__" app/` – проверить на dynamic code execution
  - `grep -rn "PASSWORD\|SECRET\|TOKEN" app/ | grep -v "os.getenv"` – hardcoded secrets check
- [ ] `.devcontainer/devcontainer.json`:
  - Убедиться, что python extensions установлены
  - Проверить settings (linter, formatter, test discovery)

### D15: Final Render deployment readiness
- [ ] Создать `RENDER_DEPLOYMENT_CHECKLIST.md`:
  - ENV variables (список обязательных)
  - Webhook URL setup (https://yourapp.onrender.com/webhook/{SECRET_PATH})
  - KIE callback URL (https://yourapp.onrender.com/callbacks/kie)
  - Health check endpoint (`/health`)
- [ ] Проверить `render.yaml` (если используется):
  - Correct start command (`python main_render.py`)
  - ENV vars placeholders
  - Health check path (`/health`)

## 📊 Progress Tracking

**Total gates:** 15  
**Completed:** 9 ✅  
**In progress:** 1 🔄  
**Remaining:** 5 ⏳  

**Estimated completion:** ~2–3 hours work (with testing)

---

*Last updated: 2026-01-11 16:20 UTC*
