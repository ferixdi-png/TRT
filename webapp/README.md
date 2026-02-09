# 🚀 TRT Mini App (Telegram Web App)

## 📁 Структура

```
webapp/
├── __init__.py
├── README.md              # Этот файл
├── api/
│   ├── __init__.py
│   ├── auth.py           # Аутентификация Telegram WebApp
│   └── routes.py         # API endpoints
└── static/
    └── index.html        # Frontend (HTML/JS)
```

## ⚙️ Настройка

### Environment Variables (Render)

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `WEBAPP_URL` | ✅ Да | URL для Mini App (например: `https://your-bot.onrender.com/webapp`) |

**Пример:**
```
WEBAPP_URL=https://trt-bot.onrender.com/webapp
```

### Активация

1. Добавить `WEBAPP_URL` в Render Environment Variables
2. Сделать git push для деплоя
3. Кнопка "🚀 Открыть приложение" появится в главном меню бота

## 🔧 API Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/webapp/` | GET | Главная страница Mini App |
| `/webapp/api/health` | GET | Health check |
| `/webapp/api/user/me` | GET | Текущий пользователь (требует initData) |
| `/webapp/api/user/{user_id}/balance` | GET | Баланс пользователя |
| `/webapp/api/models` | GET | Список доступных моделей |
| `/webapp/api/models/{model_id}` | GET | Информация о модели |
| `/webapp/api/user/{user_id}/history` | GET | История генераций |

## 🔐 Аутентификация

Mini App использует стандартную аутентификацию Telegram WebApp:

1. Telegram передает `initData` при открытии Mini App
2. Frontend отправляет `initData` в заголовке `X-Telegram-Init-Data`
3. Backend проверяет подпись через HMAC-SHA256
4. Если подпись верна - возвращает данные пользователя

## 🎨 Frontend

Frontend использует:
- Vanilla JavaScript (без фреймворков для простоты)
- Telegram WebApp JS SDK
- Адаптивный дизайн под тему Telegram

### Возможности:
- ✅ Отображение баланса
- ✅ Список моделей
- ✅ Информация о пользователе
- ✅ Адаптация под тему Telegram (светлая/темная)

## 🚀 Деплой

Mini App автоматически деплоится вместе с ботом на Render.

**Новые зависимости:**
- `aiohttp-asgi>=0.1.0` - для интеграции FastAPI в aiohttp
- `fastapi` - уже в requirements.txt

## 📝 Расширение

Для добавления новых функций:

1. **Новый API endpoint** - добавить в `webapp/api/routes.py`
2. **Новая страница** - создать HTML в `webapp/static/`
3. **Новая логика** - использовать существующие модули из `app/`

### Пример нового endpoint:

```python
@webapp_api.post("/api/generate")
async def start_generation(
    model_id: str,
    params: dict,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data")
):
    user_id = get_user_id_from_init_data(x_telegram_init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Использовать существующую логику генерации
    from app.generations.universal_engine import run_generation
    result = await run_generation(user_id, model_id, params)
    return result
```

## ❓ FAQ

**Q: Почему кнопка не появляется в меню?**
A: Проверьте что `WEBAPP_URL` установлен в Render Environment Variables

**Q: Mini App не открывается?**
A: Проверьте что URL корректный и сервис запущен

**Q: Ошибка 401 Unauthorized?**
A: Mini App должен открываться только через Telegram, не напрямую в браузере
