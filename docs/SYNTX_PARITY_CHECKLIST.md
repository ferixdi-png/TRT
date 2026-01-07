# Syntx parity checklist (TRT)

Этот чеклист нужен для регулярной проверки “Syntx parity” по слоям. Отмечайте
прохождение в релизных/стабилизационных циклах.

## UI / Wizard
- [ ] Все 42 enabled моделей видны в UI (фильтры/форматы/категории не скрывают модели)
- [ ] Wizard корректно собирает обязательные поля (prompt / image_url / audio_url / video_url)
- [ ] Confirm блокируется, если обязательный media input отсутствует (дружелюбная ошибка + кнопка “Назад”)
- [ ] Назад/В меню/Отмена доступны везде без “мёртвых” callback

## Payments
- [ ] FREE-модели не требуют reserve/charge, но пишут историю
- [ ] Paid‑модели: reserve → createTask → success → charge; fail → refund
- [ ] Нет двойных списаний; отмена корректно освобождает резерв

## Retries / Cancel
- [ ] Idempotency key не допускает дублей
- [ ] Cancel корректно завершает поток без “зависших” задач
- [ ] Таймауты возвращают понятный ответ пользователю

## Media validation
- [ ] Для image/audio/video обязательен upload или URL (если предусмотрено схемой)
- [ ] Неверный формат медиа возвращает подсказку без падений
- [ ] Missing media не запускает генерацию

## Logging / Trace
- [ ] request_id единый на весь путь
- [ ] stage + model_id + payload_hash логируются на ключевых этапах
- [ ] upstream_code/upstream_msg логируются при ошибках

## Admin / Ops
- [ ] /healthz и /readyz возвращают корректные статусы
- [ ] /health возвращает JSON для мониторинга
- [ ] В логах не раскрывается webhook secret (masking)

## Rate-limit
- [ ] Rate‑limit не блокирует webhook health endpoints
- [ ] При превышении лимита пользователь получает понятную ошибку

## Analytics hooks
- [ ] generation events пишутся в success/fail
- [ ] pricing/FX логируются для paid моделей

---

## Быстрый статический аудит (результат)

### Потенциальные дубли env-конфига (проверить единый источник)
- `PRICING_MARKUP` читается в `app/utils/config.py` и `app/payments/pricing_contract.py`
- `WEBHOOK_BASE_URL` / `PUBLIC_URL` / `RENDER_EXTERNAL_URL` / `PUBLIC_BASE_URL` используются в разных местах
- `USD_RUB_RATE` и `USD_TO_RUB_FALLBACK` разделены между pricing/FX

### Кандидаты на “мёртвые” флаги (требуют проверки usage/документации)
- `MODEL_SYNC_ENABLED` используется в `app/kie/fetch.py` и `app/tasks/model_sync.py`
- `SAFE_TEST_MODE` семейство в `app/utils/safe_test_mode.py` (проверьте, что включение отражено в docs)

### Потенциальные места утечки секретов (проверить маскирование)
- Логи webhook URL/paths (использовать mask_path/mask_webhook_url)
- Логи callback URL и token headers (не должны печатать токены целиком)
