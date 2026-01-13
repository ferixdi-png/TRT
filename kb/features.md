# Features

Статус фич: READY (production), IN_PROGRESS (разработка), PLANNED (бэклог).

## READY (Production)

### Core Bot Features
- ✅ **/start**: Welcome message + main menu
- ✅ **Main menu**: Inline keyboard с основными действиями
- ✅ **Help**: Инструкции по использованию
- ✅ **Balance**: Показ текущего баланса пользователя

### Image Generation
- ✅ **Text-to-Image**: Генерация изображения по текстовому промпту
- ✅ **Model selection**: Выбор из доступных KIE.ai моделей (20+ моделей)
- ✅ **Parameter customization**: Настройка размера, стиля, количества изображений
- ✅ **Result delivery**: Отправка готового изображения в чат
- ✅ **Job tracking**: Статус генерации (pending → processing → completed)

### Payment System
- ✅ **Balance management**: Пополнение через Telegram Stars
- ✅ **Transaction history**: История операций (пополнение + списание)
- ✅ **Price calculation**: Автоматический расчёт стоимости генерации
- ✅ **KIE callback webhook**: Обработка уведомлений о платежах

### Admin Features
- ✅ **Admin panel**: Доступ для ADMIN_IDS
- ✅ **User management**: Просмотр пользователей и балансов
- ✅ **Manual balance adjustment**: Ручное изменение баланса (для промо/компенсаций)
- ✅ **System stats**: Метрики по использованию

### Infrastructure
- ✅ **Singleton lock**: PostgreSQL advisory lock для single-instance
- ✅ **ACTIVE/PASSIVE modes**: Graceful degradation при деплое
- ✅ **Fast-ack webhook**: 200 OK < 500ms, обработка в фоне
- ✅ **Health endpoint**: /health с диагностикой (lock, queue, db)
- ✅ **Update deduplication**: Защита от дублирующих update_id
- ✅ **Database migrations**: Идемпотентные SQL миграции

## IN_PROGRESS

_(Пусто — все текущие фичи в production)_

## PLANNED (Backlog)

### Enhanced Generation
- 📋 **Image-to-Image**: Генерация на основе загруженного изображения
- 📋 **Video generation**: Поддержка text-to-video моделей
- 📋 **Batch generation**: Множественная генерация за один запрос
- 📋 **Style presets**: Предустановленные стили (anime, realistic, cartoon)

### User Experience
- 📋 **Favorites**: Сохранение промптов и результатов
- 📋 **Generation history**: Просмотр прошлых генераций
- 📋 **Referral system**: Реферальные бонусы за приглашения
- 📋 **Notifications**: Уведомления о завершении длительных генераций

### Monetization
- 📋 **Subscription tiers**: Месячная подписка с включёнными генерациями
- 📋 **Promo codes**: Промокоды на скидку/бонусный баланс
- 📋 **Free tier**: Ограниченное количество бесплатных генераций для новых пользователей

### Analytics
- 📋 **Usage analytics**: Детальная статистика по моделям, пользователям
- 📋 **Revenue dashboard**: Tracking доходов и конверсий
- 📋 **A/B testing**: Тестирование UX изменений

### Infrastructure
- 📋 **Multi-instance support**: Horizontal scaling (если нагрузка вырастет)
- 📋 **Redis caching**: Кеширование метаданных моделей
- 📋 **CDN for results**: Быстрая доставка сгенерированных изображений
- 📋 **Backup/restore**: Автоматические бэкапы базы данных

## NOT PLANNED (Explicitly Out of Scope)

- ❌ Локальная AI inference (только KIE.ai API)
- ❌ Другие мессенджеры (только Telegram)
- ❌ Web интерфейс (только Telegram bot)
- ❌ NFT/blockchain интеграция
- ❌ Social features (sharing, communities)

## Feature Toggles (ENV)

Некоторые фичи управляются через ENV:
- `WELCOME_BALANCE_RUB`: Стартовый бонус для новых пользователей (по умолчанию 0)
- `KIE_STUB`: Режим заглушки (для тестирования без реального KIE.ai API)
- `DRY_RUN`: Режим dry-run (логи без реальных операций)

## Feature Dependencies

```
Image Generation
  ↓ depends on
  - KIE.ai API доступен
  - User balance > generation cost
  - ACTIVE mode (не PASSIVE)

Payment Processing
  ↓ depends on
  - KIE callback webhook настроен
  - Database write access
  - ACTIVE mode

Admin Panel
  ↓ depends on
  - user_id in ADMIN_IDS env
  - Database read access
```

## Performance Constraints

- **Generation time**: 30 seconds - 5 minutes (зависит от модели и параметров)
- **Webhook response**: < 500ms (критично!)
- **Balance check**: < 100ms
- **Menu rendering**: < 200ms
- **Admin stats**: < 2 seconds

## Known Limitations

1. **Single instance**: Только один ACTIVE instance обрабатывает webhook (по дизайну)
2. **No streaming**: Генерация не показывает прогресс (ограничение KIE.ai API)
3. **No cancellation**: Нельзя отменить запущенную генерацию
4. **File size limit**: Telegram file size limit 50MB для изображений
