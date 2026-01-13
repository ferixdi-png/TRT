# PRODUCTION READY - TRT Bot

**Дата**: 2026-01-12  
**Версия**: 1.0.0-PRODUCTION  
**Статус**: 🔄 В ПРОЦЕССЕ АУДИТА

---

## 🎯 Одна команда для проверки

```bash
python3 tools/prod_check.py --detailed
```

**Критерий готовности**: Exit code 0 = ALL GREEN

---

## 📊 Статус по фазам

### ✅ PHASE A: Инвентаризация (COMPLETE)

**Карта потоков**:
```
UI (Telegram) 
  → Flow Builder (bot/handlers/flow.py)
  → Validation (app/kie/generator.py)
  → Pricing/Free Logic (app/pricing/)
  → KIE Client (app/integrations/kie_client.py)
  → createTask → taskId
  → Callback (main_render.py:kie_callback)
  → Storage Update (app/storage/)
  → Telegram Delivery (smart sender)
```

**Модели**:
- Всего: 72 модели
- FREE: 4 модели (z-image, qwen/text-to-image, qwen/image-to-image, qwen/image-edit)
- Категории: image(27), video(23), audio(4), enhance(6), other(8), avatar(2), music(2)
- Провайдеры: 18 (bytedance, qwen, flux2, google, kling, и др.)

**Инструменты**:
- `tools/audit_system.py` - полный анализ SOURCE_OF_TRUTH
- `tools/prod_check.py` - комплексная проверка готовности
- `AUDIT_RESULT.json` - детальные результаты

### ✅ PHASE B: Единый контракт инпутов (COMPLETE)

**Реализовано**:
- ✅ app/models/input_schema.py - парсинг required/optional/enum
- ✅ Интеграция в generator.py - валидация перед createTask
- ✅ UI запрашивает ВСЕ required поля
- ✅ Enum inputs → кнопки выбора (НЕ дефолты)
- ✅ Тесты: valid inputs, missing required, invalid enum, unknown model
- ✅ 7 enum полей: aspect_ratio, image_size, style, quality, output_format, resolution, duration, acceleration

### ⏳ PHASE C: Надёжность job lifecycle (PENDING)

**Задачи**:
- [ ] createTask → job создаётся ВСЕГДА
- [ ] Callback обновляет job и триггерит доставку
- [ ] Deferred callbacks для race condition

### ✅ PHASE D: PASSIVE MODE (COMPLETE)

**Реализовано**:
- ✅ /start отвечает даже в деградации
- ✅ Пользователь получает "Бот обновляется (20-60 сек)"
- ✅ Callback не теряется
- ✅ Порт открывается мгновенно (<0.5s)

### ⏳ PHASE E: Платежи/баланс/рефералка (PENDING)

**Задачи**:
- [ ] Reserve/commit/release баланса
- [ ] Idempotency keys
- [ ] Рефералка с защитой от дублей

### ✅ PHASE F: E2E тесты (FRAMEWORK COMPLETE)

**Реализовано**:
- ✅ tools/e2e_free_models.py обновлен для 2x прогонов
- ✅ Стабильность отслеживается: STABLE/UNSTABLE/FAILED
- ✅ Таблица метрик per-model
- ✅ Exit code 0 = все stable, 1 = есть нестабильность

**Использование**:
```bash
# DRY RUN (stub mode)
E2E_RUNS=2 python3 -m tools.e2e_free_models

# REAL RUN (реальные запросы к Kie.ai)
RUN_E2E=1 ADMIN_ID=<telegram_id> E2E_RUNS=2 python3 -m tools.e2e_free_models
```

**Статус**: Framework готов, требуется REAL RUN для финальной верификации
- [ ] Unit tests
- [ ] Smoke tests (webhook/callbacks/health)
- [ ] E2E FREE models (2 прогона)
- [ ] Отчёт-таблица с метриками

---

## 🧪 Тестирование

### FREE Models E2E Test

```bash
# DRY RUN (без реальных запросов)
python3 tools/e2e_free_models.py

# REAL RUN (с реальными запросами и Telegram delivery)
RUN_E2E=1 ADMIN_ID=<your_telegram_id> python3 tools/e2e_free_models.py
```

**Ожидаемый результат**:
```
============================================================
z-image
============================================================
[INFO] Testing z-image: ['prompt', 'aspect_ratio']
[INFO] Task created: e15c4100... (TTFB: 2.81s)
[INFO] ✅ Job found in storage
[INFO] ✅ STORAGE-FIRST | Job done via callback
✅ z-image: done (31.2s)

============================================================
SUMMARY: 4/4 passed, 0 failed
METRICS:
  - callback_4xx: 0
  - job_not_found: 0
  - avg_ttfb: 2.45s
  - avg_total_time: 42.3s
  - telegram_delivery: Check your Telegram (chat_id=...) for 4 results
============================================================
```

### Production Check

```bash
python3 tools/prod_check.py --detailed
```

**Проверяет**:
1. SOURCE_OF_TRUTH валидность
2. Environment variables
3. Миграции
4. Критичные файлы
5. Python syntax

---

## 📈 Метрики Production-Ready

| Метрика | Цель | Статус |
|---------|------|--------|
| FREE models E2E | 100% pass (2 runs) | ⏳ TODO |
| Callback 4xx rate | 0% | ⏳ TODO |
| Job not found | 0 | ⏳ TODO |
| Telegram delivery | 100% | ⏳ TODO |
| Avg TTFB | <3s | ⏳ TODO |
| Port startup | <1s | ✅ PASS |
| Passive mode response | Always | ✅ PASS |

---

## 🚀 Деплой на Render

### Pre-Deploy Checklist

- [ ] `python3 tools/prod_check.py` → Exit code 0
- [ ] `RUN_E2E=1 ADMIN_ID=... python3 tools/e2e_free_models.py` → 4/4 pass
- [ ] Все migrations применяются без ошибок
- [ ] Environment variables установлены

### Post-Deploy Verification

```bash
# 1. Проверка логов на Render
grep "Database schema ready" logs.txt  # Должно быть ✅

# 2. Проверка метрик
grep "callback_job_not_found_count" logs.txt  # Должно быть 0

# 3. Healthcheck
curl https://your-app.onrender.com/health  # Должно быть 200

# 4. Тест /start в Telegram
# Бот должен ответить в течение 1s
```

---

## 🔧 Troubleshooting

### "Бот не отвечает"
- ✅ Проверено: PASSIVE MODE теперь отвечает
- Проверь логи: `grep "PASSIVE MODE" logs.txt`
- Должно быть сообщение "Бот обновляется"

### "relation does not exist"
- ✅ Исправлено: Миграции в background_initialization()
- Проверь: `runtime_state.db_schema_ready = true`

### "Генерация не возвращает результат"
- Проверь callback: `grep "KIE_CALLBACK" logs.txt`
- Проверь orphan jobs: `callback_job_not_found_count` должно быть 0

---

## 📝 Changelog

### 2026-01-12 - PHASE A Complete
- ✅ Системный аудит (audit_system.py)
- ✅ Production check (prod_check.py)
- ✅ Карта потоков построена
- ✅ 72 модели инвентаризированы
- ✅ 4 FREE модели для E2E определены

### 2026-01-12 - PASSIVE MODE Fixed
- ✅ Порт НЕ блокируется (lock в фоне)
- ✅ PASSIVE MODE отвечает пользователю
- ✅ Миграции в background без блокировки

### 2026-01-12 - Migrations Fixed
- ✅ DROP CASCADE для идемпотентности
- ✅ Индекс на external_task_id
- ✅ Schema ready barrier

---

## ⏭️ Next Steps

1. **PHASE B**: Единый контракт инпутов
   - Парсинг required/optional/enum из SOURCE_OF_TRUTH
   - UI validation перед createTask
   - Payload preview

2. **PHASE C**: Job lifecycle hardening
   - Deferred callbacks
   - Replay mechanism

3. **PHASE E**: Платежи/баланс audit
   - Idempotency
   - Reserve/commit/release

4. **PHASE F**: E2E тесты
   - 2x прогон FREE моделей
   - Отчёт с метриками

---

**Для проверки готовности**: `python3 tools/prod_check.py` → Exit code 0 = ✅ PROD-READY
