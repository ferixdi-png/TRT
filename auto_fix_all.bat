@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================================
echo  🤖 ПОЛНОСТЬЮ АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ПРОЕКТА
echo ============================================================
echo.
echo  Этот скрипт будет:
echo  ✅ Мониторить логи на Render
echo  ✅ Находить ошибки
echo  ✅ Автоматически исправлять код
echo  ✅ Коммитить и пушить изменения в GitHub
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

%PYTHON_CMD% -c "import git" >nul 2>&1
if %errorlevel% neq 0 (
    echo 📥 Устанавливаю GitPython...
    %PYTHON_CMD% -m pip install GitPython --quiet
)

echo ✅ Все зависимости установлены
echo.

REM Проверка переменных окружения
if "%RENDER_API_KEY%"=="" (
    echo ⚠️  RENDER_API_KEY не установлен
    set /p RENDER_API_KEY="Введите ваш RENDER_API_KEY: "
    if "!RENDER_API_KEY!"=="" (
        echo ❌ API ключ обязателен!
        pause
        exit /b 1
    )
)

if "%RENDER_SERVICE_ID%"=="" (
    echo ⚠️  RENDER_SERVICE_ID не установлен
    set /p RENDER_SERVICE_ID="Введите ваш RENDER_SERVICE_ID (srv-xxxxx): "
    if "!RENDER_SERVICE_ID!"=="" (
        echo ❌ Service ID обязателен!
        pause
        exit /b 1
    )
)

if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo ⚠️  TELEGRAM_BOT_TOKEN не установлен
    set /p TELEGRAM_BOT_TOKEN="Введите ваш TELEGRAM_BOT_TOKEN: "
    if "!TELEGRAM_BOT_TOKEN!"=="" (
        echo ❌ Bot Token обязателен!
        pause
        exit /b 1
    )
)

echo.
echo 🚀 Запуск автоматического исправления...
echo.

%PYTHON_CMD% auto_fix_all.py

pause







