# UX Map: User Journeys Bot ↔ Mini App
## TRT Telegram Bot + Mini App

---

## Journey A: Newbie → First Free Generation

### Bot Flow
```
1. /start
   └→ Welcome message + main menu
   └→ Показан баланс + бесплатные генерации (5/5)

2. User taps "🎨 Создать"
   └→ Shows generation types menu
   
3. User selects type (e.g., "🎨 Текст → Фото")
   └→ Shows models list with prices
   └→ Free models marked with 🆓
   
4. User selects model
   └→ Shows model info + input requirements
   └→ Clear labels: "Опишите изображение" / "Загрузите фото"
   
5. User enters prompt
   └→ Validation: min/max length, required fields
   └→ Price confirmation screen
   
6. User confirms
   └→ Balance/free gen check
   └→ Generation starts
   └→ Progress: "⏳ Генерирую..."
   
7. Result delivered
   └→ Image/video sent to chat
   └→ "🔄 Повторить" button
   └→ Balance updated
```

### Mini App Flow (if WEBAPP_URL set)
```
1. User opens Mini App
   └→ Models catalog loaded
   └→ Balance shown in header
   
2. User selects model
   └→ Model info + UX schema displayed
   └→ Input fields with labels/hints
   
3. User fills form + uploads media (if needed)
   └→ Client-side validation
   └→ Size limit: 20MB
   
4. User submits
   └→ POST /webapp/generate
   └→ Job created, polling starts
   
5. Job status polling
   └→ GET /webapp/job/{job_id}
   └→ Status: pending → running → success/failed
   
6. Result
   └→ Image/video URL displayed
   └→ Download button
```

---

## Journey B: Paying User → Repeated Generations

### Top-up Flow (Bot)
```
1. User taps "💰 Пополнить баланс"
   └→ Shows payment options
   └→ Telegram Stars / other methods
   
2. User selects amount
   └→ Pre-checkout query
   └→ Payment processed
   
3. Payment successful
   └→ Balance updated atomically
   └→ Confirmation message
```

### Repeated Generation
```
1. User has history
   └→ /history or "📜 История" button
   
2. User can retry from history
   └→ Same params, new job
   └→ Balance check before start
   
3. Deduction flow
   └→ AFTER successful result (charge_balance_once)
   └→ Idempotent by task_id
   └→ No double charges on retry
```

---

## Dead-ends Fixed (2026-02-09)

| Issue | Status | Fix |
|-------|--------|-----|
| Webapp no balance charge | ✅ Fixed | Added charge_balance_once after success |
| Prompt required for i2v | ✅ Fixed | Made optional for image-to-video |
| Path traversal upload | ✅ Fixed | Regex + resolve() validation |
| File size no limit | ✅ Fixed | MAX_UPLOAD_SIZE = 20MB |
| int() exception | ✅ Fixed | try/except handling |

---

## Input Requirements

### By Model Type

| Type | Required Inputs | Optional |
|------|-----------------|----------|
| t2i (text-to-image) | prompt | aspect_ratio, style |
| i2i (image-to-image) | image, prompt | strength |
| t2v (text-to-video) | prompt | duration, resolution |
| i2v (image-to-video) | image | prompt, duration |
| audio | prompt or audio | voice, speed |

### UX Schema
- Labels in RU/EN
- Placeholders with examples
- Min/max constraints
- Required indicators
- Validation errors with hints

---

## Error Handling

| Error | Bot Message | Mini App Response |
|-------|-------------|-------------------|
| Insufficient balance | "💳 Недостаточно средств" + top-up button | `{"error": "Insufficient balance", "balance": X, "price": Y}` 402 |
| Invalid input | "❌ Ошибка валидации" + hint | `{"validation_errors": [...]}` 400 |
| Provider failure | "⚠️ Сервис временно недоступен" + retry | `{"error": "...", "status": "failed"}` |
| Timeout | "⏱ Превышено время ожидания" | Job status = failed |

---

## Consistency Checks

| Feature | Bot | Mini App | Match? |
|---------|-----|----------|--------|
| Model list | ✅ from kie_catalog | ✅ from /webapp/models | ✅ |
| Prices | ✅ price_resolver | ✅ price_resolver | ✅ |
| Free counter | ✅ FREE_GENERATIONS_PER_DAY | ✅ free_remaining | ✅ |
| Balance | ✅ get_user_balance | ✅ /webapp/user/{id}/balance | ✅ |
| UX labels | ✅ translations.py | ✅ ux_schema | ⚠️ Verify |

