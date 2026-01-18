# TRT_REPORT.md

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
- **Стало:** GitHubStorage использует per-request `ClientSession` без шаринга между event loop, исключая loop mismatch.
- **П1:** language selection не включён в handlers; default=ru, запись языка только при явном выборе пользователем.

## Как проверил
- Локальные проверки не запускались в этой среде.

## Какие файлы тронул
- `app/storage/github_storage.py`
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
