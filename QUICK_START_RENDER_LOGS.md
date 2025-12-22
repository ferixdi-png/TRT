# 🚀 Быстрый старт: Получение логов с Render

## 📋 Шаг 1: Получите API ключ Render

1. Откройте https://dashboard.render.com/
2. Перейдите в **Settings** → **API Keys**
3. Создайте новый ключ и скопируйте его

## 📋 Шаг 2: Найдите Service ID

1. Откройте ваш сервис в Render Dashboard
2. Service ID находится в URL: `https://dashboard.render.com/web/srv-xxxxx`
3. Или используйте команду: `python get_render_logs.py --list-services`

## 📋 Шаг 3: Установите переменные окружения

```cmd
set RENDER_API_KEY=your_api_key_here
set RENDER_SERVICE_ID=srv-xxxxx
```

## 📋 Шаг 4: Запустите скрипт

**Простой способ (Windows):**
```cmd
get_render_logs_simple.bat
```

**Или через Python:**
```cmd
python get_render_logs.py --service-id srv-xxxxx --lines 200 --analyze
```

## 🔍 Анализ проблемы 409

Если видите ошибки 409 в логах:

1. **Остановите все экземпляры:**
   - На Render: Suspend → подождите 10 сек → Resume
   - Локально: `taskkill /F /IM python.exe`

2. **Удалите webhook:**
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true
   ```

3. **Проверьте дублирующие сервисы** в Render Dashboard

4. **Перезапустите** сервис на Render

---

**Подробная инструкция:** см. `RENDER_LOGS_GUIDE.md`







