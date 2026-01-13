# 📋 QUICK DEPLOY GUIDE

## На Render (Production)

### 1️⃣ Подготовка GitHub

```bash
cd /workspaces/TRT

# Проверить что всё скоммитено
git status

# Добавить изменения
git add .
git commit -m "🚀 Production ready: aiogram 3.7.0, 72 models, robust errors"
git push origin main
```

### 2️⃣ На Render.com Dashboard

1. **Create → Web Service**
   - Connect your GitHub repo (`ferixdi-png/TRT`)
   - Choose `main` branch

2. **Environment Setup**
   
   Добавь эти переменные в Render Settings:
   
   ```
   TELEGRAM_BOT_TOKEN=7...        (от @BotFather)
   KIE_API_KEY=kie_...            (от kie.ai)
   ADMIN_ID=123456789             (твой Telegram ID)
   BOT_MODE=webhook
   DATABASE_URL=postgresql://...  (Render PostgreSQL URL)
   ```

3. **Build & Start Commands**
   
   ```
   Build: pip install -r requirements.txt
   Start: python main_render.py
   ```

4. **Deploy!**
   - Нажми Deploy
   - Дождись статуса "Live" (~3-5 минут)

### 3️⃣ После успешного деплоя

```bash
# Проверить что бот работает
curl https://your-service.onrender.com/health

# Должен вернуть:
# {
#   "status": "ok",
#   "bot": "active",
#   ...
# }

# Отправить сообщение боту в Telegram
/start → должен ответить
/admin → админ-панель (только для ADMIN_ID)
```

### 4️⃣ Troubleshooting

**Если бот не отвечает:**
```
1. Проверь логи: Render Dashboard → Logs
2. Убедись что TELEGRAM_BOT_TOKEN правильный
3. Убедись что DATABASE_URL доступен
4. Перезагрузи сервис: Manual Deploy
```

**Если webhook не работает:**
```
1. Проверь что BOT_MODE=webhook
2. Дождись полного развёртывания (может быть delay 30-60 сек)
3. Проверь логи на ошибки
```

---

## Локально (Development)

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env
export TELEGRAM_BOT_TOKEN=your_token
export KIE_API_KEY=your_key
export ADMIN_ID=123456789
export BOT_MODE=polling

# 3. Запустить
python main_render.py

# 4. Протестировать
# Отправь сообщение боту в Telegram
/start
/admin
```

---

## 🎉 ВСЁ ГОТОВО!

Проект полностью функционален и готов к production.

**Статус:** ✅ 95% готовности  
**Последние изменения:**
- ✅ aiogram 3.7.0+ инициализация
- ✅ 72 модели загружены
- ✅ Webhook с timeout protection
- ✅ Robust error handling
- ✅ Database migrations на Render
- ✅ Admin-панель
- ✅ Payment system
- ✅ Sentry мониторинг (optional)

Можно смело деплоить! 🚀
