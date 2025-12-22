# 📋 RENDER LOGS - QUICK START

**3 шага для подключения к логам Render**

## 🚀 БЫСТРЫЙ СТАРТ

### Шаг 1: Установите API ключ

```bash
# Windows
set RENDER_API_KEY=your_api_key_here

# Linux/Mac
export RENDER_API_KEY=your_api_key_here
```

**Где взять API ключ:**
1. Откройте https://dashboard.render.com/
2. Settings → API Keys
3. Создайте новый ключ

### Шаг 2: Найдите Service ID

**Вариант A: Автоматически**
```bash
python scripts/render_logs.py --list-services
```

**Вариант B: Вручную**
1. Откройте ваш сервис в Render Dashboard
2. Service ID в URL: `https://dashboard.render.com/web/srv-xxxxx`

**Вариант C: Из конфига**
Если у вас есть `services_config.json`, Service ID будет взят оттуда автоматически.

### Шаг 3: Получите логи

**Последние 100 строк:**
```bash
python scripts/render_logs.py --service-id srv-xxxxx
```

**Отслеживание в реальном времени (tail/follow):**
```bash
python scripts/render_logs.py --service-id srv-xxxxx --tail
```

**С фильтрами:**
```bash
# Только ошибки
python scripts/render_logs.py --service-id srv-xxxxx --level ERROR

# Поиск по тексту
python scripts/render_logs.py --service-id srv-xxxxx --text "409 Conflict"

# За последние 15 минут
python scripts/render_logs.py --service-id srv-xxxxx --since 15m

# Комбинация фильтров
python scripts/render_logs.py --service-id srv-xxxxx --tail --level ERROR --text "error" --since 1h
```

---

## 📊 ВОЗМОЖНОСТИ

### Фильтры

- `--level ERROR|WARNING|INFO` - фильтр по уровню
- `--text "текст"` - поиск по тексту
- `--since 15m|2h|1d` - фильтр по времени

### Режимы

- **Обычный** - показывает последние N строк и выходит
- **Tail/Follow** (`--tail`) - отслеживает логи в реальном времени

### Анализ

- `--analyze` - автоматический анализ ошибок, предупреждений, конфликтов 409

---

## 💡 ПРИМЕРЫ

### Просмотр последних ошибок
```bash
python scripts/render_logs.py --service-id srv-xxxxx --level ERROR --lines 50
```

### Мониторинг конфликтов 409
```bash
python scripts/render_logs.py --service-id srv-xxxxx --tail --text "409" --interval 10
```

### Поиск конкретной ошибки
```bash
python scripts/render_logs.py --service-id srv-xxxxx --text "ImportError" --since 1h
```

---

## ✅ ПРОВЕРКА

После запуска вы должны увидеть:
- ✅ Логи в консоли
- ✅ Форматированный вывод с timestamp
- ✅ Фильтры работают корректно

Если видите ошибки:
- Проверьте `RENDER_API_KEY`
- Проверьте `RENDER_SERVICE_ID` или используйте `--service-id`
- Проверьте интернет-соединение

---

**ГОТОВО! Теперь вы можете легко получать логи Render одной командой.**







