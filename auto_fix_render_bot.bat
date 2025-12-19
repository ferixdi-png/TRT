@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================================
echo  АВТОМАТИЧЕСКИЙ МОНИТОРИНГ И ИСПРАВЛЕНИЕ БОТА НА RENDER
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

REM Проверка переменных окружения
if "%RENDER_API_KEY%"=="" (
    echo ⚠️  RENDER_API_KEY не установлен
    echo.
    echo 💡 Как получить API ключ:
    echo    1. Откройте https://dashboard.render.com/
    echo    2. Settings → API Keys
    echo    3. Создайте новый ключ
    echo.
    set /p RENDER_API_KEY="Введите ваш RENDER_API_KEY: "
    if "!RENDER_API_KEY!"=="" (
        echo ❌ API ключ обязателен!
        pause
        exit /b 1
    )
)

if "%RENDER_SERVICE_ID%"=="" (
    echo ⚠️  RENDER_SERVICE_ID не установлен
    echo.
    set /p RENDER_SERVICE_ID="Введите ваш RENDER_SERVICE_ID (srv-xxxxx): "
    if "!RENDER_SERVICE_ID!"=="" (
        echo ❌ Service ID обязателен!
        pause
        exit /b 1
    )
)

if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo ⚠️  TELEGRAM_BOT_TOKEN не установлен
    echo.
    set /p TELEGRAM_BOT_TOKEN="Введите ваш TELEGRAM_BOT_TOKEN: "
    if "!TELEGRAM_BOT_TOKEN!"=="" (
        echo ❌ Bot Token обязателен!
        pause
        exit /b 1
    )
)

echo.
echo 🚀 Запуск автоматического мониторинга...
echo    - Проверка каждые 60 секунд
echo    - Автоматическое удаление webhook'ов
echo    - Автоматическое исправление конфликтов 409
echo.
echo Нажмите Ctrl+C для остановки
echo.

%PYTHON_CMD% auto_fix_render_bot.py

pause
