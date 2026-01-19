# TRT_REPORT.md

## 2026-01-19: P0/P1 production hardening — media delivery, free tools, pricing, modality contract
**Было → стало (ключевые изменения):**
- **Было:** Telegram получал прямые URL и падал на HTML/403/redirect. **Стало:** медиа всегда скачивается сервером, проверяется content-type/size и отправляется как InputFile; для oversized — безопасная ссылка без preview. 【F:app/generations/media_pipeline.py†L1-L278】【F:app/generations/telegram_sender.py†L1-L180】
- **Было:** Wizard иногда просил фото в text→image и смешивал модальности. **Стало:** введён `model_mode`, авто-нормализация required для image/text и корректный первичный ввод; Nano Banana Pro выведен из text→image. 【F:models/kie_models.yaml†L1-L2170】【F:app/models/yaml_registry.py†L1-L167】【F:bot_kie.py†L313-L452】【F:kie_models.py†L2736-L2837】
- **Было:** цены округлялись до int и минимум 1 ₽. **Стало:** фикс курс 77.83, маржа x2, ceil до 0.01 без min=1. 【F:pricing/config.yaml†L1-L42】【F:app/config.py†L79-L141】【F:app/services/pricing_service.py†L1-L102】
- **Было:** free tools “плавающие” и смешивались с категориями. **Стало:** 5 самых дешёвых моделей фиксированы в pricing config, исключены из остальных категорий; лимит 5/час + referral банк. 【F:pricing/config.yaml†L1-L42】【F:app/services/free_tools_service.py†L1-L120】【F:bot_kie.py†L1532-L5166】【F:kie_models.py†L2736-L2837】
- **Было:** кнопка “Баланс” шумела 404. **Стало:** 404 кэшируется на 6 часов, UX “KIE недоступен” без ошибок. 【F:helpers.py†L96-L220】
- **Было:** базовый smoke зависел от GitHub storage env. **Стало:** run_smoke использует JSON storage по умолчанию. 【F:scripts/run_smoke.py†L14-L110】

**Тесты/проверки:**
- `python scripts/verify_project.py`
- `pytest -q`
- `python -m compileall .`
- `python scripts/run_smoke.py`

## 2026-01-19: Production gate + universal media delivery + credits + session lifecycle + offline smoke
**Root cause mapping (лог-инциденты → фиксы):**
- `telegram.error.BadRequest: Wrong type of the web page content` → введён универсальный бинарный media pipeline c проверкой content-type, KIE download-url и fallback на InputFile.【F:app/generations/media_pipeline.py†L1-L250】
- `KIE credits endpoint 404 (/api/v1/account/balance)` → фикс на `/api/v1/chat/credit` + UX “KIE credits temporarily unavailable”.【F:app/kie/kie_client.py†L479-L597】【F:helpers.py†L124-L176】
- `aiohttp Unclosed client session/connector` → единый KIE ClientSession, закрытие в post_shutdown и тест-leak guard.【F:app/bootstrap.py†L82-L151】【F:tests/test_aiohttp_leak_check.py†L1-L19】
- `GEN_ERROR KIE_FAIL_STATE` → редактирование recordInfo (redaction) + чистый UX с retry + структурные логи.【F:app/observability/redaction.py†L1-L35】【F:app/generations/failure_ui.py†L1-L18】【F:bot_kie.py†L13257-L13313】
- `DATABASE_URL not set - skipping singleton lock` → детерминированная конкуренция через GitHub SHA-retry + per-user lock в балансах (no lost updates).【F:app/storage/github_storage.py†L240-L360】【F:app/services/user_service.py†L12-L48】

**Было → стало (ключевые изменения):**
- **Было:** Telegram получал URL, возвращающий HTML/JSON. **Стало:** resolve_and_prepare_telegram_payload проверяет content-type и всегда отдаёт бинарный InputFile/документ при HTML/unknown. 【F:app/generations/media_pipeline.py†L1-L250】
- **Было:** KIE credits шёл на неактуальный endpoint и падал 404. **Стало:** `/api/v1/chat/credit` + UX “KIE credits temporarily unavailable” при сбое. 【F:app/kie/kie_client.py†L479-L597】【F:helpers.py†L124-L214】
- **Было:** aiohttp сессии не закрывались. **Стало:** единый KIE client + close() на shutdown и leak-тест. 【F:app/bootstrap.py†L82-L151】【F:tests/test_kie_client_lifecycle.py†L1-L25】
- **Было:** KIE fail state отдавал сырые детали без UX. **Стало:** редактированные логи + кнопка Retry + чистый текст с correlation_id. 【F:app/observability/redaction.py†L1-L35】【F:app/generations/failure_ui.py†L1-L18】【F:bot_kie.py†L13257-L13313】
- **Было:** риск конфликтов без DB lock. **Стало:** per-user lock в user_service + GitHub sha retry. 【F:app/services/user_service.py†L12-L48】【F:app/storage/github_storage.py†L240-L360】
- **Было:** отсутствовал универсальный release gate. **Стало:** scripts/production_gate.py + offline smoke всех 72 моделей. 【F:scripts/production_gate.py†L1-L44】【F:scripts/smoke_all_models_offline.py†L1-L170】

**Файлы изменены (основные):**
- `app/generations/media_pipeline.py`, `app/generations/telegram_sender.py`, `app/generations/failure_ui.py`
- `app/kie/kie_client.py`, `app/bootstrap.py`, `app/services/user_service.py`, `app/observability/redaction.py`
- `app/generations/universal_engine.py`, `app/generations/kie_job_runner.py`, `bot_kie.py`, `helpers.py`
- `scripts/production_gate.py`, `scripts/smoke_all_models_offline.py`
- `tests/test_media_pipeline.py`, `tests/test_telegram_sender_media.py`, `tests/test_kie_credits.py`, `tests/test_kie_fail_state.py`, `tests/test_aiohttp_leak_check.py`, `tests/test_user_balance_lock.py`, `tests/test_kie_client_lifecycle.py`, `tests/test_recordinfo_redaction.py`

**Команды проверки (выполнены):**
- `python scripts/verify_project.py` → OK
- `pytest -q` → OK
- `python scripts/production_gate.py` → OK

## 2026-01-19: P0/P1 hardening — webhook, KIE gating, media delivery, credits UX
**Было (P0/P1):**
- Webhook падал с 500 из‑за попыток обращаться к `correlation_id` на `telegram.Update` (slots), без гарантированного fallback‑ответа пользователю.
- KIE stub включался в проде по умолчанию, если не задан `ALLOW_REAL_GENERATION`/`KIE_ALLOW_REAL`.
- Telegram отдавал `Wrong type of the web page content` при отправке медиа по URL (часть моделей ломала доставку).
- KIE credits ходил на `/api/v1/account/balance` и получал 404 без явного UX‑сообщения.
- Ошибки `state=fail` не показывали `failCode/failMsg` в логах и сообщениях, стадийные логи не фиксировали duration для create/poll/parse/send.

**Стало:**
- Webhook логирует correlation_id через contextvars, не мутирует Update и всегда ACK=200; при ошибке обработчика отправляется fallback‑сообщение пользователю.
- Реальный KIE включается по умолчанию, если есть `KIE_API_KEY` и нет `TEST_MODE`/`KIE_STUB=1`; stub только по явному флагу.
- Telegram sender выбирает метод доставки по `ModelSpec.output_media_type`, делает URL→download fallback с content‑type guard, media‑group и size‑guard.
- KIE credits переехал на `/api/v1/chat/credit`, при 404 показывает “Баланс KIE недоступен (endpoint 404)” и пишет structured warning.
- Ошибки `state=fail` включают `failCode/failMsg` в structured logs и тексте пользователю; стадии create/poll/parse/send фиксируют duration.

**Root cause:**
- Ошибка корреляции в webhook и fallback‑обработка, неверные defaults по stub, слабый медиа‑детектор и устаревший endpoint balance.

**Файлы изменены:**
- `main_render.py`, `app/generations/telegram_sender.py`, `app/generations/universal_engine.py`, `app/integrations/kie_stub.py`
- `app/kie/kie_client.py`, `bot_kie.py`, `helpers.py`, `.dockerignore`
- `tests/test_webhook_handler_smoke.py`, `tests/test_kie_stub_env_logic.py`, `tests/test_telegram_sender_media.py`
- `TRT_REPORT.md`

**Как проверил:**
- `python scripts/verify_project.py`
- `pytest -q`

**Как проверить вручную (Telegram):**
1. `/start` → выбрать модель → отправить промпт → убедиться, что медиа доставляется корректным типом (фото/видео/аудио).
2. Админ → “Панель администратора” → убедиться, что баланс KIE отображается или “Баланс KIE недоступен (endpoint 404)”.
3. Спровоцировать ошибку генерации (например, некорректные параметры) → увидеть `failCode/failMsg` и correlation_id в сообщении.
4. Проверить webhook‑режим: отправить update и убедиться, что ответ всегда 200 и пользователь получает fallback при ошибке.

## 2026-01-19: P0/P1 fixes — balance, payment flow, session reset
**Было:**
- Кнопка “Баланс” падала при отсутствии `get_credits()` у KIE клиента.
- `pay_sbp:*` уходил в UNKNOWN_CALLBACK и сбрасывал пользователя в меню.
- PTBUserWarning фиксировал возврат state=3, неизвестный текущему ConversationHandler.
- “Грязные сессии”: ожидание `payment_screenshot` конфликтовало с меню/моделью.

**Стало:**
- Баланс показывает внутренние RUB всегда; KIE credits — best‑effort без падений и с нейтральным текстом.
- `pay_sbp:*` и `pay_card:*` маршрутизируются корректно и поддерживаются из MENU при валидной сессии.
- Возвраты из button_callback ограничены валидными state keys (без PTBUserWarning).
- Введён единый reset при навигации: очищает хвосты сценариев при переходе в меню/модели/баланс/реферальную информацию.

**Root cause:**
- В клиенте KIE отсутствовал `get_credits()`, а payment callback не был зарегистрирован в роутере/known patterns.

**Файлы изменены:**
- `app/kie/kie_client.py`, `helpers.py`, `bot_kie.py`
- `tests/test_balance_kie_safe.py`, `tests/test_payment_flow_sbp.py`, `tests/test_navigation_resets_session.py`, `tests/test_callbacks_routing.py`
- `TRT_REPORT.md`

**Статус:**
- payment flow OK
- balance OK
- no unknown_callback
- no PTBUserWarning

**Как проверил:**
- `pytest tests/test_balance_kie_safe.py tests/test_payment_flow_sbp.py tests/test_navigation_resets_session.py tests/test_callbacks_routing.py`

## 2025-02-16: Production-ready generation pipeline (stub/real, media, logs, tests)
**Было:**
- KIE stub возвращал `state=completed` и `resultJson.urls`, что ломало `universal_engine` (ожидает `state=success` и `resultUrls`).
- Реальный KIE выключался из-за дефолта `KIE_STUB=1`, что оставляло прод на stub.
- `wait_for_task()` ожидал только `completed`, из-за чего `success` не завершал poll.
- Парсер результатов плохо различал text/image/video/audio и не логировал структурно пустые ответы.
- UX после подтверждения мог быть «тихим» до финального результата.

**Стало:**
- Stub возвращает `state=success` и корректный `resultJson` (urls/text) + структурные логи.
- Реальный KIE используется только при `KIE_ALLOW_REAL=1`/`ALLOW_REAL_GENERATION=1` и наличии `KIE_API_KEY`; stub включается явно.
- `wait_for_task()` обрабатывает `success`/`completed`.
- Парсер результата определяет media type по данным/SSOT, поддерживает text/image/video/audio/voice/document, логирует пустые ответы с `error_code`.
- После confirm пользователь сразу получает «✅ Принято / Генерирую…», плюс структурные логи по всем этапам (create/poll/parse/tg).

**Root cause:**
- Несоответствие контрактов stub ↔ universal_engine и дефолтный `KIE_STUB=1` скрывали реальный KIE, а poll ждал неверное состояние.

**Файлы изменены:**
- `app/integrations/kie_stub.py`, `app/kie/kie_client.py`, `app/generations/universal_engine.py`, `app/generations/telegram_sender.py`
- `app/observability/error_catalog.py`, `main_render.py`, `bot_kie.py`
- `tests/test_kie_stub_success.py`, `tests/test_generation_modalities_flow.py`, `tests/test_universal_engine_ssot.py`
- `TRT_REPORT.md`

**Как проверил:**
- `python scripts/verify_project.py`
- `pytest -q`

## 2025-02-16: P0/P1 hardening (trace, callbacks, async balance, dedup, KIE e2e)
**Было:**
- `trace_event()` падал на дублирующемся `stage` → ломал `answerCallbackQuery` и UX.
- Callback data с двоеточием в значении (`set_param:aspect_ratio:9:16`) разбивался неправильно в парсере.
- `check_balance` и другие async пути дергали sync‑обертки, что приводило к `RuntimeError` в event loop.
- UNKNOWN_CALLBACK молча уводил в меню без структурного лога и fix_hint.
- Повторные update_id могли дублировать `/start` и callback цепочки.
- Шумный `CATALOG_CACHE hit` в INFO.

**Стало:**
- `trace_event()` теперь best‑effort, не пробрасывает исключения, корректно принимает `stage` без дублей.
- Все разборы callback data используют `split(..., maxsplit=...)`; колоны в значении не ломают парсер.
- Баланс/лимиты теперь получают данные через async путь без sync‑wrapper.
- UNKNOWN_CALLBACK отвечает пользователю и пишет structured log с `fix_hint`.
- Введён TTL‑dedup по `update_id` (outcome=deduped) для защиты от повторов.
- `CATALOG_CACHE hit` переведён в DEBUG.

**Покрытие тестами:**
- `tests/ux/test_z_image_aspect_ratio_flow.py` — callback с `9:16` (не уходит в UNKNOWN_CALLBACK).
- `tests/test_check_balance_button.py` — кнопка баланса без `SYNC_WRAPPER_CALLED_IN_ASYNC`.
- `tests/test_kie_job_runner_e2e.py` — 5 e2e кейсов KIE (image/video/audio/stt/photo enhancement).

**Как проверил:**
- `pytest -q`

## 2025-02-16: P0 webhook ACK + correlation via contextvars
**Проблема:**
- `/webhook` падал с 500 из‑за `object.__setattr__(update, "correlation_id", ...)` на `telegram.Update` (slots).
- При падении PTB обработчика Telegram ретраил webhook → UX «молчит».

**Исправления:**
- Убрано добавление атрибутов в `Update`. Корреляция теперь хранится в contextvars (request‑scoped) и доступна через `app.observability.trace.get_correlation_id()`.
- `/webhook` всегда возвращает 200 при валидном JSON и корректном секрет‑токене, даже если PTB обработка упала.
- Добавлено логирование цепочки `update_received → forwarded_to_ptb (queued) → handler_outcome` без падений.

**Как проверить:**
- `python scripts/verify_project.py`
- `pytest -q` (есть тест webhook ACK: POST /webhook ⇒ 200 + лог `forwarded_to_ptb`).

## Что нашёл в коммитах (последние 3 дня)
- `app/kie_catalog/models_pricing.yaml` — расширения прайс-таблицы (commit `0ea378e5`, см. `git diff 0ea378e5^ 0ea378e5`).
- Серия коммитов 2026-01-17 затрагивала startup/handlers/logging, но прайс/реестр моделей в корне остаётся `models/kie_models.yaml` + `app/kie_catalog/models_pricing.yaml`.

## Файлы — source of truth (registry / pricing / menu / config)
1. `models/kie_models.yaml`
   - Зачем: **registry** моделей (model_type + input) — канонический источник модели и параметров.
   - Кто читает: `app/models/yaml_registry.py` → `app/models/registry.py`.
   - Этап: **startup** (проверка + загрузка) и далее для меню/маршрутов.

2. `app/kie_catalog/models_pricing.yaml`
   - Зачем: **pricing catalog** (официальные цены в USD, credits, типы моделей).
   - Кто читает: `app/kie_catalog/catalog.py` и `app/services/pricing_service.py`.
   - Этап: **startup** (проверка) и далее для карточек и цены.

3. `pricing/config.yaml` (fallback `pricing/config.json`)
   - Зачем: **курс и мультипликатор** для RUB (usd_to_rub, markup_multiplier).
   - Кто читает: `pricing/engine.py` → `app/config.py`.
   - Этап: **startup** (чтение настроек в Settings).

4. Меню
   - Меню строится из registry + pricing: `app/helpers/models_menu.py`, `app/helpers/models_menu_handlers.py`.
   - Каталог берётся из `app/kie_catalog/models_pricing.yaml`, параметры модели — из `models/kie_models.yaml`.

## Bisect (GOOD/BAD)
- Использован `git bisect` (GOOD=`4b111def`, BAD=`HEAD`) с проверкой на регрессию источника моделей и fallback-каллаbacks.
- По результату `git bisect` первый BAD определён как `e9378870a66f65266643f91a78c34fa7938d1704`.
- Дальнейшее уточнение требует полноценного runtime-теста (`/start` + callback) с .env.

## Было → Стало
- **Было:** главное меню ломало HTML при чанкинге и иногда отправлялось без parse_mode.
- **Стало:** HTML-чанки нормализуются (баланс тегов, закрытие/переоткрытие), parse_mode всегда HTML.
- **Было:** первое сообщение /start могло быть перегружено рамками и длинными секциями, клавиатура терялась среди чанков.
- **Стало:** первый экран = короткий welcome + клавиатура; подробности уходят отдельными сообщениями без клавиатуры.
- **Было:** input_parameters мог доходить до конца без ответа (NO-SILENCE violation при waiting_for=prompt).
- **Стало:** для prompt всегда есть ответ (валидация, сохранение, переход к следующему шагу), fallback guard прикрывает тишину.
- **Было:** GitHubStorage держал общие aiohttp-сессии между loop, что приводило к `session_detached`/`loop_mismatch`.
- **Стало:** GitHubStorage использует управляемую сессию с проверкой loop mismatch и явным закрытием на shutdown; метрики чтения/записи включают latency.
- **Было:** optional параметры могли не иметь кнопки “Пропустить/по умолчанию”, а подсказки обещали кнопку, которой нет.
- **Стало:** для optional enum/boolean/text добавлены кнопки “Использовать по умолчанию” или “Пропустить (auto)” с корректными подсказками.
- **Было:** image→video модели начинали с prompt, из-за чего prompt мог не запрашиваться после фото.
- **Стало:** порядок первого ввода определяется по model_type + schema (image→video сначала фото, text→video сначала prompt, audio сначала файл).
- **П1:** language selection не включён в handlers; default=ru, запись языка только при явном выборе пользователем.

## Как проверил
- `pytest -q`

## Какие файлы тронул
- `app/storage/github_storage.py`
- `bot_kie.py`
- `tests/test_parameter_buttons.py`
- `scripts/kie_smoke.py`
- `TRT_REPORT.md`

## Почему теперь не отвалится в webhook режиме
- `create_application()` в `app/bootstrap.py` сразу после `Application.builder().build()` вызывает `ensure_error_handler_registered()`, поэтому webhook-строитель всегда получает error handler.
- `app/main.py` и `bot_kie.py` используют тот же инвариант, чтобы исключить путь запуска без error handler.

## Логи (до / после)
**До:**
- `📊 models_registry source=unknown count=...`
- `PRICE_RUB=... MULT=... RATE=100.0 ...`
- `MAIN_MENU_SHOWN source=unknown_callback_handler`

**После (ожидаемо):**
- `✅ SOURCE OF TRUTH: registry=/workspace/TRT/models/kie_models.yaml models=... | pricing_catalog=/workspace/TRT/app/kie_catalog/models_pricing.yaml models=... | pricing_settings=/workspace/TRT/pricing/config.yaml | usd_to_rub=77.2222 | price_multiplier=2.0`
- `📊 models_registry source=yaml path=/workspace/TRT/models/kie_models.yaml count=...`
- `MAIN_MENU_SHOWN source=gen_type` (fallback не используется)

## PTB ConversationHandler warning
- В коде ConversationHandler использует `per_message=False` (default) и включает `CallbackQueryHandler` + `MessageHandler` для текстовых/медиа шагов. Это вызывает PTBUserWarning:
  - `If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message`.
- Это безопасно для текущего UX, потому что состояние ведётся по `per_chat` и сообщения/кнопки ожидаются в рамках чата пользователя.
- Исправление через `per_message=True` невозможно без удаления MessageHandler из ConversationHandler (сломает ввод текста/медиа). Поэтому warning задокументирован как допустимый компромисс.

## Runbook: локальный Render-mode smoke (без секретов)
1. Убедитесь, что `python` доступен, затем:
   - `python scripts/render_webhook_smoke.py`
2. Скрипт стартует `main_render.py` в `BOT_MODE=webhook`, поднимает health server, вызывает `/health` и `/webhook`.
   - Для sandbox/CI используется `SMOKE_NO_PROCESS=1` (skip Telegram init, без внешнего сетевого вызова).
3. Ожидаемый результат:
   - `status=ok` в JSON ответа `/health`
   - `webhook_route_registered=true` в JSON ответа
   - `/webhook` возвращает 200/204

## Runbook: верификация на Render
1. Deploy текущей ветки.
2. В Render logs найти маркеры:
   - `[HEALTH] server_listening=true port=...`
   - `[WEBHOOK] route_registered=true`
   - `[RUN] webhook_set_ok=true` (если не используется WEBHOOK_SKIP_SET)
   - `POST /webhook status=200` (при ручном тесте)
   - отсутствие `HTML chunk invalid`
   - отсутствие `NO-SILENCE VIOLATION`
   - отсутствие `Unclosed client session`
3. Проверить `/health` = 200 и JSON содержит `webhook_route_registered=true`.

## Что не проверено в этой среде
- Реальные Render логи и Telegram-сценарии: требуется доступ к Render/Telegram с .env (секреты не доступны в sandbox).

## 2025-02-14: UX contract + safe KIE mode + structured callback log
**Было:**
- Не было формального UX/State/Log контрактов в docs/.
- KIE stub включался только при явном `KIE_STUB=1`.
- Structured log для callback был неформализован.

**Стало:**
- Добавлены UX/State/Log контракты в `docs/` как соглашение для дальнейшей реализации.
- Safe-mode для KIE: по умолчанию используется stub, реальный режим только при `KIE_ALLOW_REAL=1`.
- Добавлен structured callback log (correlation_id/action_path/waiting_for/param/outcome).

**Причина:**
- Зафиксировать UX как контракт и обеспечить безопасный режим интеграций по умолчанию.

**Как проверил:**
- `pytest -q`

**Что осталось:**
- Интегрировать router parse→validate→route→execute→respond→log во все callback-ветки.
- Доработать тесты UX/лог-контрактов по списку в задании.

## 2025-02-14: Wizard UX для input_parameters + параметры/назад
**Было:**
- После prompt для не z-image моделей цепочка параметров обрывалась: следующий шаг не показывался, логировалось `input_parameters reached end without response`.
- NO-SILENCE guard выдавал ложный warning даже при наличии исходящих ответов.
- Back возвращал в начало с удалением параметров, отсутствовал стек истории.
- На confirmation не было единой кнопки для просмотра/изменения всех параметров.
- Текст “не вовремя” отвечал общим “Я не жду текст сейчас” без контекстных подсказок.

**Стало:**
- Исправлено ветвление в `input_parameters`: после установки параметра всегда переход к следующему шагу или подтверждению; special-case z-image больше не захватывает общий флоу.
- NO-SILENCE guard в конце `input_parameters` больше не логирует нарушение при `outgoing_count > 0`.
- Реализован `param_history` стек: push при вводе параметров, pop при `back_to_previous_step` для корректного возврата.
- Добавлена кнопка “⚙️ Параметры” на экране подтверждения, список параметров с текущими значениями и быстрым редактированием.
- Для “текста не вовремя” показывается контекстная подсказка с кнопками продолжения и примером действия.

**Причина:**
- Устранить прод-симптомы из логов и сделать ввод параметров “невозможно сломать”.

**Как проверил:**
- `pytest`

**Какие файлы тронул:**
- `bot_kie.py`
- `tests/test_input_parameters_wizard_flow.py`

## 2025-02-15: Callback crash fix + single main menu UX
**Причина бага:**
- `NameError: is_admin_user is not defined` при обработке `set_param` → `calculate_price_rub` (отсутствовала инициализация is_admin_user перед расчетом цены).

**Где исправил:**
- `bot_kie.py` в обработчике `set_param` добавлено `is_admin_user = get_is_admin(user_id)` перед `calculate_price_rub` и сброс `waiting_for` после ввода последнего параметра.

**Как устранил “второе меню”:**
- `show_main_menu` теперь отправляет только одно сообщение с welcome + клавиатурой (без вторичных release/what's new карточек).
- `unknown_callback_handler` и fallback в `button_callback` отвечают коротким сообщением и редактируют текущее сообщение в главное меню без дополнительных карточек.

**Как проверил:**
- Команды: `python scripts/verify_project.py`, `pytest -q`.
- UX шаги (через harness): `/start -> gen_type:text-to-image -> select_model:z-image -> prompt -> set_param:aspect_ratio:1:1` — без исключений, подтверждение генерации отображается, главное меню не дублируется.

**Какие файлы тронул:**
- `bot_kie.py`
- `tests/test_main_menu.py`
- `tests/ux/test_z_image_aspect_ratio_flow.py`
- `TRT_REPORT.md`

## 2025-02-15: Универсальный engine + SSOT coverage (72 модели)
**Сделано:**
- Введён единый ModelSpec, собираемый из SSOT (`models/kie_models.yaml` + `app/kie_catalog/models_pricing.yaml`), с полями schema/output_media_type.
- Wizard/engine/payload используют единый pipeline без хардкодов под одну модель.
- Унифицированный parser результата и отправка в Telegram по `media_type`.

**Покрытие по моделям:**
- Авто-smoke проверяет 72/72 моделей (schema + payload build).
- Media buckets: image, video, audio, voice, text покрыты мок-тестами.

**Ручные проверки:**
- В этой среде не выполнялись (нет доступа к Telegram/KIE).

**Как проверил:**
- `python scripts/verify_project.py`
- `pytest -q`

## 2025-02-15: ABSOLUTE TRACEABILITY (corr-id + stages)
**Было:**
- Корреляция между UI → KIE → TG отсутствовала, TRACE_IN/TRACE_OUT не гарантировались.
- PRICE_RUB логировался дублирующе при каждом расчёте.
- Ошибки не имели единой taxonomy/fix_hint.

**Стало:**
- Добавлен unified trace logger: `app/observability/trace.py` (corr-id, TRACE_IN/OUT, stage + duration). 
- Корреляция прокидывается в UI/SESSION/KIE/TG пайплайн; ключевые стадии: `UI_ROUTER`, `SESSION_LOAD`, `STATE_VALIDATE`, `PRICE_CALC`, `KIE_CREATE`, `KIE_POLL`, `KIE_PARSE`, `TG_DELIVER`.
- Telegram delivery вынесен в `deliver_result()` с логированием типа медиа, метода отправки и fallback.
- Цена логируется только в `select_model` и финальном подтверждении; дублирование устранено.
- Добавлен каталог ошибок `app/observability/error_catalog.py` и структурированный `trace_error` в error handler.

**Как включать детализацию:**
- `LOG_LEVEL=DEBUG` — stacktrace в trace_error и больше деталей.
- `TRACE_VERBOSE=true` — расширенные поля в trace_event.
- `TRACE_PAYLOADS=false` — не логирует сырые prompt/media (только len/hash).
- `TRACE_PRICING=true` — детальнее price-каталог.

**Пример поиска по корреляции:**
- `grep "corr-<update_id>-<user_id>" render.log`

**Как проверил:**
- `python scripts/verify_project.py`
- `pytest -q`

## 2025-02-14: P0 set_trace_context + TRACE unification + catalog cache

### STEP 0 — FULL AUDIT
**Где вызывался guard.set_trace_context:**
- `bot_kie.py` → `button_callback` (≈L3320).
- `bot_kie.py` → `input_parameters` (≈L9761).
- `bot_kie.py` → `confirm_generation` (≈L12492).
- `bot_kie.py` → `unknown_callback_handler` (≈L25738).

**Текущая сигнатура NoSilenceGuard.set_trace_context:**
- `app/observability/no_silence_guard.py`:
  `def set_trace_context(self, *, user_id, chat_id, update_id, message_id=None, update_type=None, correlation_id=None, **extra)`

**Где update_id передавался дважды (и падал на бою):**
- `button_callback`: `guard.set_trace_context(update_id, correlation_id, update_id=update_id, ...)` — позиционный + keyword.
- `input_parameters`: `guard.set_trace_context(update_id, correlation_id, update_id=update_id, ...)` — позиционный + keyword.
- `confirm_generation` и `unknown_callback_handler` — аналогичный паттерн.

**Почему тесты не ловили:**
- Большинство unit-тестов вызывали обработчики напрямую или через harness без реального callback→input потока, поэтому конфликт аргументов возникал только при боевом пути Telegram callback + message (Render webhook), где вызывался `button_callback`/`input_parameters` с positional+keyword аргументами.

**Какие пути боевые падали:**
- Любой callback → `button_callback` или вход текста → `input_parameters`, когда `update_id` передавался дважды.
- На Render это проявлялось при клике любой кнопки (callback) и при вводе параметра (message).

### STEP 1 — FIX P0
- `set_trace_context` переведён на keyword-only и все вызовы исправлены на именованные аргументы.
- Исключены все дубли `update_id` (позиционный + keyword).

### STEP 2 — TESTS
- Добавлен e2e тест: `/start -> callback gen_type:text-to-image -> callback select_model:z-image -> user sends prompt`.
- Добавлен тест на `set_trace_context` с keyword-only вызовом.

### STEP 3 — TRACE UNIFICATION
- `TRACE_VERBOSE`, `TRACE_PAYLOADS`, `TRACE_PRICING` подключены в `trace_event`.
- Корреляция: webhook correlation_id теперь пробрасывается в PTB handlers через `update.correlation_id`.
- Все логи `🔥🔥🔥` переведены на DEBUG.

### STEP 4 — PERFORMANCE
- Добавлен process-level cache по mtime ключу для каталога `models_pricing.yaml` + registry `models/kie_models.yaml`.
- Логируются `CATALOG_CACHE hit/miss + load_ms`.
- `get_free_model_ids()` использует кеш `load_catalog()`.

### STEP 7 — REPORT + PROOF
**Как включить расширенные логи:**
- `LOG_LEVEL=DEBUG`
- `TRACE_VERBOSE=true`
- `TRACE_PAYLOADS=true` (если нужно видеть payload)
- `TRACE_PRICING=true` (если нужно видеть цены)

**grep по correlation_id:**
- `rg "correlation_id=<id>" -n`

**E2E ручные сценарии (10 кликов):**
1. `/start` → главное меню
2. `gen_type:text-to-image` → список моделей
3. `select_model:z-image` → запрос prompt
4. Ввести prompt → запрос следующего параметра
5. `back_to_previous_step` → возврат шага
6. `back_to_menu` → сброс сессии и главное меню
7. `free_tools` → список бесплатных
8. `help_menu` → справка
9. `check_balance` → баланс
10. `generate_again` → повтор генерации
