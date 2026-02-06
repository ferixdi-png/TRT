# 📋 КОНФИГУРАЦИЯ НЕСКОЛЬКИХ СЕРВИСОВ RENDER

## 🎯 Назначение

Если у вас несколько сервисов в Render, подключенных к одному GitHub проекту, но с разными токенами Telegram ботов, используйте файл `services_config.json` для настройки мониторинга всех сервисов.

## 📝 Формат конфигурации

Создайте файл `services_config.json` в корне проекта:

```json
{
  "services": [
    {
      "name": "Основной бот",
      "service_id": "srv-d4s025er433s73bsf62g",
      "telegram_token": "8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y",
      "enabled": true
    },
    {
      "name": "Тестовый бот",
      "service_id": "srv-xxxxxxxxxxxxx",
      "telegram_token": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
      "enabled": true
    },
    {
      "name": "Резервный бот",
      "service_id": "srv-yyyyyyyyyyyyy",
      "telegram_token": "9876543210:ZYXwvutsRQPonmlkJIHgfedcba",
      "enabled": false
    }
  ],
  "render_api_key": "YOUR_RENDER_API_KEY",
  "default_service": "YOUR_RENDER_SERVICE_ID"
}
```

## 🔧 Параметры

### `services` (массив)
Список сервисов для мониторинга.

**Параметры каждого сервиса:**
- `name` (строка) - Имя сервиса (для отображения в логах)
- `service_id` (строка) - ID сервиса на Render (формат: `srv-xxxxx`)
- `telegram_token` (строка) - Токен Telegram бота для этого сервиса
- `enabled` (boolean) - Включён ли мониторинг этого сервиса (`true`/`false`)

### `render_api_key` (строка)
API ключ Render для доступа к логам всех сервисов.

### `default_service` (строка, опционально)
ID сервиса по умолчанию (если не указан, используется первый активный).

## 🚀 Использование

### Вариант 1: Один сервис
Если в конфиге только один активный сервис, скрипт будет мониторить только его.

### Вариант 2: Несколько сервисов
Если в конфиге несколько активных сервисов, скрипт будет:
1. Мониторить все сервисы по очереди
2. Собирать ошибки со всех сервисов
3. Создавать общий промпт для Cursor AI со всеми ошибками

## 📋 Как найти Service ID

1. Откройте Render Dashboard: https://dashboard.render.com/
2. Выберите ваш сервис
3. Service ID находится в URL: `https://dashboard.render.com/web/srv-xxxxx`
4. Или в настройках сервиса → "Service ID"

## 🔐 Безопасность

⚠️ **ВАЖНО:** Файл `services_config.json` содержит секретные данные (токены, API ключи).

**Рекомендации:**
1. Добавьте `services_config.json` в `.gitignore`:
   ```
   services_config.json
   ```

2. Создайте шаблон `services_config.json.example`:
   ```json
   {
     "services": [
       {
         "name": "Пример сервиса",
         "service_id": "srv-xxxxx",
         "telegram_token": "YOUR_TOKEN_HERE",
         "enabled": true
       }
     ],
     "render_api_key": "YOUR_API_KEY_HERE",
     "default_service": "srv-xxxxx"
   }
   ```

3. Закоммитьте только `.example` файл, не сам `services_config.json`

## 🔄 Fallback режим

Если файл `services_config.json` не найден, скрипт использует переменные окружения:
- `RENDER_API_KEY`
- `RENDER_SERVICE_ID`
- `TELEGRAM_BOT_TOKEN`

Это обеспечивает обратную совместимость со старыми настройками.

## ✅ Пример использования

1. Создайте `services_config.json` с вашими сервисами
2. Запустите `cursor_ai_integration.bat`
3. Скрипт автоматически обнаружит все активные сервисы
4. Будет мониторить все сервисы и создавать общий промпт для Cursor AI







