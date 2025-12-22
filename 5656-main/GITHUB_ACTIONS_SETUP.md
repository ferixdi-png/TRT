# 🔄 GitHub Actions - Автоматический CI/CD

**Дата:** 2025-12-19

---

## 🎯 ЦЕЛЬ

Автоматический деплой на Render через GitHub Actions:
- Push в `main` → CI проверяет → Deploy на Render
- Без ручных действий
- Без необходимости "просить новый чат" в Cursor

---

## 📋 НАСТРОЙКА (ОДИН РАЗ)

### 1. GitHub Secrets

Перейди в: **GitHub Repository → Settings → Secrets and variables → Actions → New repository secret**

Добавь следующие Secrets:

#### Обязательные (выбери один вариант):

**Вариант A: Render Deploy Hook (предпочтительно)**
- `RENDER_DEPLOY_HOOK` = `https://api.render.com/deploy/srv-XXXXX?key=XXXXX`
  - Получи из: Render Dashboard → Service → Settings → Deploy Hook

**Вариант B: Render API (fallback)**
- `RENDER_API_KEY` = `rnd_XXXXX...`
  - Получи из: Render Dashboard → Account Settings → API Keys
- `RENDER_SERVICE_ID` = `srv-XXXXX...`
  - Получи из: Render Dashboard → Service → Settings → Service ID

#### Опциональные:

- `RENDER_HEALTH_URL` = `https://your-service.onrender.com`
  - Для health check после деплоя

---

## 🔄 КАК РАБОТАЕТ

### CI Workflow (`.github/workflows/ci.yml`)

**Триггеры:**
- Pull Request в `main`
- Push в `main`

**Шаги:**
1. Checkout code
2. Setup Python 3.11
3. Install dependencies (`pip install -r requirements.txt`)
4. Set test environment (`APP_ENV=test`, `FAKE_KIE_MODE=1`)
5. Run `verify_project.py`
6. Run `behavioral_e2e.py`
7. Check for silence violations
8. Check singleton lock protection
9. Upload artifacts

**FAIL если:**
- `verify_project.py` не проходит
- `behavioral_e2e.py` находит молчащие модели
- `artifacts/behavioral/summary.md` не содержит "100% MODELS RESPONDED"
- Singleton lock не найден в коде

---

### Deploy Workflow (`.github/workflows/deploy_render.yml`)

**Триггеры:**
- После успешного CI на `main`
- Push тегов `v*` (например, `v1.0.0`)

**Шаги:**
1. Checkout code
2. Deploy via Render Deploy Hook (если `RENDER_DEPLOY_HOOK` установлен)
   ИЛИ
   Deploy via Render API (если `RENDER_API_KEY` + `RENDER_SERVICE_ID` установлены)
3. Wait 30 seconds
4. Health check (если `RENDER_HEALTH_URL` установлен)
5. Generate deploy summary

**FAIL если:**
- Deploy hook/API возвращает ошибку
- Health check не проходит после 10 попыток

---

## ✅ ПРОВЕРКА

### Локальная проверка CI:

```bash
# Установи тестовое окружение
export APP_ENV=test
export FAKE_KIE_MODE=1
export TELEGRAM_BOT_TOKEN=test_token
export KIE_API_KEY=test_key

# Запусти проверки
python scripts/verify_project.py
python scripts/behavioral_e2e.py
```

### Проверка workflows:

1. Создай Pull Request в `main`
2. Проверь что CI запустился автоматически
3. После CI PASS → Deploy должен запуститься автоматически

---

## 📊 АРТЕФАКТЫ

После каждого CI run доступны артефакты:
- `verification-artifacts` - все артефакты из `artifacts/`
- `behavioral-e2e-results` - результаты behavioral тестов

Скачать можно в: **GitHub → Actions → Workflow run → Artifacts**

---

## 🔍 TROUBLESHOOTING

### CI не запускается:
- Проверь что файлы `.github/workflows/*.yml` в репозитории
- Проверь что branch = `main` (или `master`)

### Deploy не запускается:
- Проверь что CI прошёл успешно
- Проверь что Secrets установлены правильно
- Проверь логи в GitHub Actions

### Health check падает:
- Проверь что `RENDER_HEALTH_URL` правильный
- Проверь что сервис действительно поднялся (может потребоваться больше времени)

---

## 📝 ПРИМЕРЫ ЗНАЧЕНИЙ (ЗАГЛУШКИ)

**НЕ ИСПОЛЬЗУЙ ЭТИ ЗНАЧЕНИЯ В PRODUCTION!**

```
RENDER_DEPLOY_HOOK=https://api.render.com/deploy/srv-xxxxx?key=xxxxx
RENDER_API_KEY=rnd_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
RENDER_SERVICE_ID=srv-xxxxxxxxxxxxxxxxxxxx
RENDER_HEALTH_URL=https://your-service.onrender.com
```

---

**ГОТОВО! После настройки Secrets всё работает автоматически! 🚀**
