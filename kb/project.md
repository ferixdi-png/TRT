# Project Overview

**Product**: TRT (Telegram Render Tool)  
**Purpose**: Telegram bot для генерации изображений и видео через KIE.ai API  
**Market**: Российский рынок (цены в RUB, оплата через Telegram Stars)  
**Status**: Production-ready, активный коммерческий продукт

## SSOT (Single Source of Truth)

**Models & Metadata**: `models/KIE_SOURCE_OF_TRUTH.json` (v1.2.10-FINAL)  
**Pricing & Margins**: Calculated from KIE_SOURCE_OF_TRUTH.json pricing field  
**ENV Contract**: `kb/deployment.md` defines all required environment variables  
**Telemetry Contract**: `app/telemetry/logging_contract.py` (event types, reason codes)  
**UI Registry**: `app/telemetry/ui_registry.py` (screens, buttons, flows)

## Deprecated / Legacy (DO NOT USE)

**Files to IGNORE in runtime**:
- `./aiogram/` folder - local stubs, shadowed by site-packages (removed in Docker build)
- `models/kie_models.yaml` - legacy format, replaced by KIE_SOURCE_OF_TRUTH.json
- `bot_kie.py` - old PTB (python-telegram-bot) runner, replaced by main_render.py
- Any `*_old.py` or `*_backup.py` files in handlers/

**Legacy Handlers** (move to /legacy if found active):
- Multiple parallel UX flows (only flow.py + z_image.py are canonical)
- Standalone model handlers (should use unified pipeline from Cycle 10+)

## Core Value Proposition

Пользователь отправляет текстовый промпт → бот генерирует изображение/видео через AI модели → результат приходит в Telegram.

Монетизация: предоплаченный баланс (RUB/Telegram Stars), списание за каждую генерацию.

## Critical Requirements

1. **Стабильность**: Zero tolerance для ERROR в production логах
2. **Быстрый отклик**: Callback queries отвечают < 1 секунды (UX requirement)
3. **Идемпотентность**: Дублирующие update_id не обрабатываются дважды
4. **Singleton**: Только один активный instance обрабатывает webhook (через PostgreSQL advisory lock)
5. **Graceful degradation**: PASSIVE mode отвечает быстро, но блокирует опасные операции

## Definition of Done (DOD)

Проект считается "доделанным", если:

- ✅ `product/truth.yaml` — единственный source of truth
- ✅ `scripts/verify.py` + `scripts/smoke.py` — зелёные в CI
- ✅ 5 consecutive deploys без ERROR/Traceback циклов
- ✅ `/health` показывает корректное состояние (ACTIVE/PASSIVE, queue, db)
- ✅ PASSIVE mode: быстрые ответы + понятные блокировки
- ✅ ACTIVE mode: end-to-end user journey работает

## Key Metrics

- **Uptime target**: 99.5%
- **P50 response time**: < 300ms (webhook fast-ack)
- **P95 response time**: < 800ms
- **Error rate**: 0 per 10 minutes (P0 errors)
- **Queue drop rate**: < 1%
- **Lock acquisition time**: < 5 seconds

## Out of Scope (Explicitly Not Doing)

- Масштабирование на N инстансов (single instance через lock достаточно для текущей нагрузки)
- Поддержка других мессенджеров (только Telegram)
- AI inference локально (только через KIE.ai API)
- Множественные энтрипоинты (только `main_render.py`)
