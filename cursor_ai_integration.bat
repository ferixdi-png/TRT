@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cls
echo ============================================================
echo  🤖 ИНТЕГРАЦИЯ С CURSOR AI ДЛЯ УМНОГО ИСПРАВЛЕНИЯ
echo ============================================================
echo.
echo  Система работает совместно с Cursor AI:
echo  ✅ Глубокий анализ структуры проекта
echo  ✅ Понимание кнопок, генераций, KIE API
echo  ✅ Создание детальных задач с контекстом
echo  ✅ Cursor AI умно исправляет ошибки
echo  ✅ Обеспечивает работу бота с нейросетями
echo  ✅ Все кнопки работают
echo  ✅ Все генерации получаются
echo.
echo  Нажмите Ctrl+C для остановки
echo ============================================================
echo.

REM Проверка Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo ❌ Python не найден!
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=python3
    )
) else (
    set PYTHON_CMD=python
)

echo ✅ Python найден
echo.

REM Проверка и установка зависимостей
echo 📦 Проверка зависимостей...
%PYTHON_CMD% -c "import requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo 📥 Устанавливаю requests...
    %PYTHON_CMD% -m pip install requests --quiet
)

echo ✅ Все зависимости установлены
echo.

REM Установка переменных окружения (fallback, если нет services_config.json)
set RENDER_API_KEY=rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw
set RENDER_SERVICE_ID=srv-d4s025er433s73bsf62g
set TELEGRAM_BOT_TOKEN=8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y

echo ✅ Переменные окружения установлены (fallback)
echo.
echo 💡 Для работы с несколькими сервисами создайте файл services_config.json
echo    См. пример в services_config.json
echo.
echo 🚀 Запуск интеграции с Cursor AI...
echo.

%PYTHON_CMD% cursor_ai_integration.py

pause




