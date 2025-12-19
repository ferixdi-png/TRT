# ✅ GITHUB ACTIONS SETUP - COMPLETE

**Дата:** 2025-12-19  
**Статус:** ✅ **READY FOR USE**

---

## 📋 СОЗДАННЫЕ ФАЙЛЫ

### GitHub Workflows:
1. `.github/workflows/ci.yml` - CI pipeline
2. `.github/workflows/deploy_render.yml` - Deploy на Render

### Скрипты:
3. `scripts/autopilot_one_command.py` - Единая команда для полного цикла

### Документация:
4. `GITHUB_ACTIONS_SETUP.md` - Полная инструкция по настройке
5. `AUTOPILOT.md` - Документация автопилота
6. `START_HERE.txt` - Быстрый старт

### Обновлённые:
7. `scripts/verify_project.py` - Добавлен behavioral_e2e
8. `README.md` - Добавлена информация о CI/CD

---

## 🔧 CI WORKFLOW (`.github/workflows/ci.yml`)

**Триггеры:**
- Pull Request в `main`
- Push в `main`

**Проверки:**
- ✅ `verify_project.py`
- ✅ `behavioral_e2e.py`
- ✅ Проверка тишины (silence violations)
- ✅ Проверка singleton lock
- ✅ Загрузка артефактов

**FAIL если:**
- Любая проверка не проходит
- Найдены молчащие модели
- Нет `artifacts/behavioral/summary.md`

---

## 🚀 DEPLOY WORKFLOW (`.github/workflows/deploy_render.yml`)

**Триггеры:**
- После успешного CI на `main`
- Push тегов `v*`

**Методы деплоя:**
1. **Render Deploy Hook** (предпочтительно) - если `RENDER_DEPLOY_HOOK` установлен
2. **Render API** (fallback) - если `RENDER_API_KEY` + `RENDER_SERVICE_ID` установлены

**После деплоя:**
- Health check (если `RENDER_HEALTH_URL` установлен)
- Summary в GitHub Actions

---

## 🔐 GITHUB SECRETS (ОДИН РАЗ)

Перейди: **Repository → Settings → Secrets and variables → Actions**

### Обязательные (выбери один):

**Вариант A (предпочтительно):**
- `RENDER_DEPLOY_HOOK` = `https://api.render.com/deploy/srv-XXXXX?key=XXXXX`

**Вариант B:**
- `RENDER_API_KEY` = `rnd_XXXXX...`
- `RENDER_SERVICE_ID` = `srv-XXXXX...`

### Опциональные:
- `RENDER_HEALTH_URL` = `https://your-service.onrender.com`

---

## ✅ ЛОКАЛЬНАЯ ПРОВЕРКА

```bash
# Установи тестовое окружение
export APP_ENV=test
export FAKE_KIE_MODE=1
export TELEGRAM_BOT_TOKEN=test_token
export KIE_API_KEY=test_key

# Запусти полный цикл
python scripts/autopilot_one_command.py

# Или отдельные проверки
python scripts/verify_project.py
python scripts/behavioral_e2e.py
```

---

## 🎯 ОЖИДАЕМОЕ ПОВЕДЕНИЕ

1. **Push в main** → CI запускается автоматически
2. **CI проверяет** → `verify_project.py` + `behavioral_e2e.py`
3. **Если PASS** → Deploy workflow запускается автоматически
4. **Deploy отправляет запрос** → Render деплоит новую версию
5. **Health check** → Проверяет что сервис поднялся

---

## 📊 АРТЕФАКТЫ

После каждого CI run:
- `verification-artifacts` - все артефакты
- `behavioral-e2e-results` - результаты behavioral тестов

Скачать: **GitHub → Actions → Workflow run → Artifacts**

---

**ГОТОВО К ИСПОЛЬЗОВАНИЮ! 🚀**
