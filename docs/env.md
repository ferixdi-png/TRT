# Environment Variables

Документация обязательных переменных окружения для TRT бота.

## Обязательные переменные

Все перечисленные ниже переменные **обязательны** для запуска бота. При отсутствии любой из них бот не запустится.
`WEBHOOK_BASE_URL` требуется только при `BOT_MODE=webhook`.

| Ключ | Назначение | Формат | Где используется |
|------|-----------|--------|------------------|
| `ADMIN_ID` | Telegram ID администратора бота | Целое число (например: `123456789`) | Админ-панель, статистика, модерация |
| `BOT_MODE` | Режим работы бота | `polling`, `webhook`, `auto`, `passive` | Определяет способ получения обновлений от Telegram |
| `DATABASE_URL` | Строка подключения к PostgreSQL | `postgresql://user:password@host:port/database` | Подключение к базе данных (Render PostgreSQL) |
| `DB_MAXCONN` | Максимальное количество соединений в пуле | Целое число > 0 (например: `10`) | Connection pooling для PostgreSQL |
| `KIE_API_KEY` | API ключ для KIE.ai | Строка (токен от KIE.ai) | Генерации через KIE API |
| `PAYMENT_BANK` | Название банка для платежей | Строка (например: `Сбербанк`) | Отображение реквизитов для оплаты |
| `PAYMENT_CARD_HOLDER` | Имя держателя карты | Строка (например: `Иванов И.И.`) | Отображение реквизитов для оплаты |
| `PAYMENT_PHONE` | Номер телефона для платежей | Строка (например: `+79991234567`) | Отображение реквизитов для оплаты |
| `PORT` | Порт для healthcheck сервера | Целое число 1-65535 (например: `8000`) | Healthcheck endpoint для Render |
| `SUPPORT_TELEGRAM` | Telegram контакт поддержки | Строка (например: `@support`) | Кнопка поддержки в боте |
| `SUPPORT_TEXT` | Текст поддержки | Строка (например: `Напишите нам в поддержку`) | Отображение информации о поддержке |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | Строка (токен от @BotFather) | Подключение к Telegram API |
| `WEBHOOK_BASE_URL` | Базовый URL для webhook | URL (например: `https://your-bot.onrender.com`) | Webhook режим работы бота |
| `WEBHOOK_URL` | Legacy alias для webhook base URL (deprecated) | URL (например: `https://your-bot.onrender.com`) | Webhook режим работы бота |

## Валидация

При старте бота выполняется автоматическая валидация:

1. **Проверка наличия** - все ключи должны быть установлены
2. **Проверка формата** - значения должны соответствовать ожидаемому формату

Для webhook-режима путь `/webhook/<secret>` строится из `WEBHOOK_SECRET`.
Если `WEBHOOK_SECRET` не задан, используется sha256-хэш `ADMIN_ID + TELEGRAM_BOT_TOKEN`,
а проверка `X-Telegram-Bot-Api-Secret-Token` выполняется только при наличии
`WEBHOOK_SECRET_TOKEN`.

Валидация выполняется в `app/utils/startup_validation.py`.

## Пример .env файла

```env
ADMIN_ID=123456789
BOT_MODE=polling
DATABASE_URL=postgresql://user:password@host:5432/database
DB_MAXCONN=10
KIE_API_KEY=your_kie_api_key_here
PAYMENT_BANK=Сбербанк
PAYMENT_CARD_HOLDER=Иванов И.И.
PAYMENT_PHONE=+79991234567
PORT=8000
SUPPORT_TELEGRAM=@support
SUPPORT_TEXT=Напишите нам в поддержку
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
WEBHOOK_BASE_URL=https://your-bot.onrender.com
# WEBHOOK_URL=https://your-bot.onrender.com  # optional legacy alias
```

## Render.com настройка

На Render.com эти переменные устанавливаются через:

1. **Dashboard → Service → Environment**
2. Добавление каждой переменной вручную
3. Или через **Connections** для `DATABASE_URL` (автоматически)

## Безопасность

⚠️ **ВАЖНО**: Никогда не коммитьте `.env` файлы в репозиторий!

- Все секретные значения маскируются в логах
- Используйте Render Environment Variables для продакшена
- Локально используйте `.env` файл (добавлен в `.gitignore`)
