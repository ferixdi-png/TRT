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
- **Было:** `models_registry source=unknown`, fallback на дефолтный RATE=100.0, отсутствующие модели в pricing.
- **Стало:** явные пути registry/pricing/настроек, валидация на старте, синхронизация pricing ↔ registry.
- **Было:** главное меню показывало только "Главное меню" без приветственного текста и блока "Версия/Дата/Что нового".
- **Стало:** /start и возврат в меню всегда показывают расширенный welcome-текст + блок релиза, кнопки меню сохраняются.
- **Было:** GitHubStorage мог использовать session из закрытого event loop → `RuntimeError: Event loop is closed`.
- **Стало:** GitHubStorage пересоздаёт session при смене loop и закрывает session после тестового подключения.

## Как проверил
- `git log --since="3 days ago" --stat`
- `git diff 0ea378e5^ 0ea378e5 --stat`
- `rg -n "pricing|prices|RUB|rate|multiplier|registry|models|menu|прайс|курс|source" ...`
- `git bisect start` + GOOD/BAD (см. секцию Bisect)
- `pytest`
- `python -m compileall -q .`

## Логи (до / после)
**До:**
- `📊 models_registry source=unknown count=...`
- `PRICE_RUB=... MULT=... RATE=100.0 ...`
- `MAIN_MENU_SHOWN source=unknown_callback_handler`

**После (ожидаемо):**
- `✅ SOURCE OF TRUTH: registry=/workspace/TRT/models/kie_models.yaml models=... | pricing_catalog=/workspace/TRT/app/kie_catalog/models_pricing.yaml models=... | pricing_settings=/workspace/TRT/pricing/config.yaml | usd_to_rub=77.2222 | price_multiplier=2.0`
- `📊 models_registry source=yaml path=/workspace/TRT/models/kie_models.yaml count=...`
- `MAIN_MENU_SHOWN source=gen_type` (fallback не используется)
