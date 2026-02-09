# UX Contract for Generation Parameters

## Карта текущего UX

### Точки ввода параметров

| Компонент | Файл | Источник параметров | Валидация |
|-----------|------|---------------------|-----------|
| **Бот - диалоги** | `bot_kie.py` | `session['properties']` → `model_spec.schema_properties` | `kie_input_builder.py` |
| **Бот - выбор параметров** | `bot_kie.py:prompt_for_specific_param()` | `properties.get(param_name)` | inline в функции |
| **Бот - ввод значений** | `bot_kie.py:input_parameters()` | `properties`, `params` | inline + `kie_input_builder` |
| **Mini App** | `webapp/static/index.html` | `/webapp/api/models`, `/webapp/api/top-models` | Нет клиентской |
| **form_engine** | `app/ux/form_engine.py` | `kie_contract/schema_loader` → `kie_models.yaml` | `validate_payload()` |

### Источники данных (текущее состояние)

```
models/kie_models.yaml          → schema_loader → form_engine
                                ↘
app/kie_catalog/models_pricing.yaml → ModelSpec.schema_properties → bot_kie.py
                                                                  ↘
app/models/input_schema.py      → (NEW) Source of Truth           → тесты
```

### Расхождения

| Проблема | Где | Влияние |
|----------|-----|---------|
| Разные источники схем | `kie_models.yaml` vs `input_schema.py` | Дублирование, рассинхрон |
| UX тексты хардкодятся | `bot_kie.py` (30K строк) | Сложно поддерживать |
| Нет единых подсказок | Везде разные | UX несогласован |
| Валидация размазана | `kie_input_builder`, `form_engine`, inline | Разные ошибки |
| Mini App без валидации | `index.html` | Ошибки на API |

---

## Целевая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCE OF TRUTH                          │
│              app/models/input_schema.py                     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ ParamSpec    │  │ ModelSchema  │  │ UX Metadata  │      │
│  │ - name       │  │ - model_id   │  │ - hints      │      │
│  │ - type       │  │ - params[]   │  │ - errors     │      │
│  │ - required   │  │ - checklist  │  │ - examples   │      │
│  │ - enum       │  │ - output     │  │ - placeholders│     │
│  │ - default    │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
    │   Bot UI      │ │  Mini App     │ │  Validation   │
    │ prompt_for_   │ │  Form         │ │  Layer        │
    │ specific_param│ │  Generator    │ │               │
    └───────────────┘ └───────────────┘ └───────────────┘
            │               │               │
            └───────────────┼───────────────┘
                            ▼
                    ┌───────────────┐
                    │ Normalization │
                    │ + API Mapping │
                    └───────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   KIE API     │
                    └───────────────┘
```

---

## Стандарт параметров

### Обязательные поля ParamSpec

| Поле | Тип | Назначение |
|------|-----|------------|
| `name` | string | API ключ параметра |
| `label_ru` / `label_en` | string | Человекочитаемое название |
| `type` | enum | string, number, integer, boolean, enum, file_url, file_urls |
| `required` | bool | Обязательность |
| `default` | any | Значение по умолчанию |

### UX поля

| Поле | Назначение |
|------|------------|
| `hint_ru` / `hint_en` | Зачем это поле, как влияет на результат |
| `placeholder_ru` / `placeholder_en` | Подсказка в пустом поле |
| `error_ru` / `error_en` | Сообщение об ошибке |
| `example` | Пример валидного значения |

### Ограничения

| Поле | Применимо к | Назначение |
|------|-------------|------------|
| `min_value` / `max_value` | number, integer | Диапазон чисел |
| `min_length` / `max_length` | string | Длина строки |
| `enum_values` | enum | Список допустимых значений |
| `max_items` | file_urls | Макс. количество файлов |

### Зависимости

| Поле | Назначение |
|------|------------|
| `depends_on` | Показывать только если установлен другой параметр |
| `depends_value` | Требуемое значение зависимости |
| `advanced` | Скрывать в базовом режиме |

---

## Правила UX текстов

### Подсказки (hints)
- **Коротко** — 1 строка, до 60 символов
- **Без техно-жаргона** — "Детальнее, но дороже" вместо "Увеличивает resolution output"
- **С пользой** — объясняет влияние на результат или цену

### Ошибки (errors)
- **Конкретно** — что не так
- **С решением** — как исправить
- **Без кодов** — "Загрузите изображение" вместо "Error 400: image_url required"

### Примеры
```
✅ "1080p — выше качество, выше цена"
✅ "Загрузите фото в формате JPG или PNG"
✅ "Минимум 10 символов описания"

❌ "Параметр resolution определяет выходное разрешение"
❌ "Error: validation failed for field 'prompt'"
❌ "Invalid input"
```

---

## Таблица моделей и параметров

### Text-to-Image

| Модель | Обязательные | Дефолты | SKU влияют на |
|--------|--------------|---------|---------------|
| `flux-2/pro-text-to-image` | prompt, resolution | resolution=1K | resolution (1K/2K) |
| `flux/kontext` | prompt, image_input, quality | quality=Pro | quality (Pro/Max) |
| `midjourney/text-to-image` | prompt | speed=fast, version=7 | speed (relaxed/fast/turbo) |

### Text-to-Video

| Модель | Обязательные | Дефолты | SKU влияют на |
|--------|--------------|---------|---------------|
| `sora-2-pro-text-to-video` | prompt | n_frames=10, size=standard | n_frames, size |
| `kling-2.6/text-to-video` | prompt, duration, sound | duration=5, sound=false | duration × sound |
| `wan/2-6-text-to-video` | prompt | duration=5, resolution=720p | duration × resolution |

### Image-to-Video

| Модель | Обязательные | Дефолты | SKU влияют на |
|--------|--------------|---------|---------------|
| `wan/2-5-image-to-video` | prompt, image_url | duration=5, resolution=1080p | duration |
| `wan/2-6-image-to-video` | prompt, image_urls | duration=5, resolution=1080p | duration × resolution |

---

## План интеграции

### Фаза 1: Расширить Source of Truth ✅
- [x] Добавить схемы для 11 критичных моделей в `input_schema.py`
- [x] Унифицировать UX тексты (hints, errors, placeholders)
- [ ] Добавить остальные 85+ моделей (по мере необходимости)

### Фаза 2: Интегрировать в бот ✅
- [x] Создать `get_param_spec()` для получения спеки параметра
- [x] Добавить `_get_ssot_param_label()`, `_get_ssot_param_hint()`, `_get_ssot_param_error()`
- [x] Функции работают с fallback на старый код

### Фаза 3: Интегрировать в Mini App ✅
- [x] API endpoint `/webapp/api/models/{model_id}` возвращает `ux_schema`
- [ ] Клиентская валидация на основе схемы (следующий шаг)
- [ ] Генерация форм из схемы (следующий шаг)

### Фаза 4: Единая валидация ✅
- [x] `validate_input()` в `input_schema.py`
- [x] `normalize_param_value()` для нормализации
- [x] 12 тестов проходят

---

## STOP/GO критерии

### GO если:
- [x] Критичные модели (11) имеют схему в Source of Truth
- [x] Бот и Mini App могут использовать одну схему
- [x] Валидация до API ловит основные ошибки
- [x] Тесты зелёные (12 тестов)
- [x] Добавление модели = запись в `input_schema.py` + минимальный glue

### NO GO если:
- [ ] ~~Параметры заданы в нескольких местах~~ → Source of Truth создан
- [ ] ~~Нет тестов на контракт~~ → 12 тестов

---

## 🚦 ФИНАЛЬНЫЙ STOP/GO ОТЧЁТ

**Дата:** 2026-02-09  
**Статус:** 🟢 **GO**

### ✅ Выполнено

| Задача | Статус | Файлы |
|--------|--------|-------|
| Карта текущего UX | ✅ | `docs/ux_parameter_contract.md` |
| Source of Truth схема | ✅ | `app/models/input_schema.py` |
| Функции интеграции | ✅ | `get_param_spec`, `validate_input`, `normalize_param_value` |
| API для Mini App | ✅ | `webapp/aiohttp_handlers.py` → `ux_schema` |
| Интеграция в бот | ✅ | `bot_kie.py` → `_get_ssot_*` функции |
| Тесты | ✅ | `tests/test_model_input_validation.py` (12 тестов) |

### 📊 Метрики

- **Моделей в Source of Truth:** 11 (критичные)
- **Тестов:** 12 (все проходят)
- **Функций интеграции:** 9
- **Сломанный функционал:** 0

### ⚠️ Остаток работы (не блокирующий)

1. Добавить схемы для остальных 74+ моделей
2. Клиентская валидация в Mini App
3. Генерация форм из схемы в Mini App

### 📁 Изменённые файлы

```
app/models/input_schema.py        # Source of Truth (991 строк)
webapp/aiohttp_handlers.py        # API endpoint ux_schema
bot_kie.py                        # _get_ssot_* функции
tests/test_model_input_validation.py  # 12 тестов
docs/ux_parameter_contract.md     # этот документ
```

### Рекомендация

**Продолжать работу.** Базовая инфраструктура Source of Truth создана и работает.
По мере добавления новых моделей или изменения существующих — добавлять схемы в `input_schema.py`.
