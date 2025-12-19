@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cls
echo ============================================================
echo  🚨 ИСПРАВЛЕНИЕ 409 CONFLICT
echo ============================================================
echo.
echo  Этот скрипт:
echo  ✅ Удаляет webhook через Telegram API
echo  ✅ Проверяет сервисы Render
echo  ✅ Создаёт промпт для Cursor AI
echo  ✅ Помогает найти и исправить проблему
echo.
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

REM Установка переменных окружения
set RENDER_API_KEY=rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw
set RENDER_SERVICE_ID=srv-d4s025er433s73bsf62g
set TELEGRAM_BOT_TOKEN=8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y

echo ✅ Переменные окружения установлены
echo.
echo 🚀 Запуск исправления 409 Conflict...
echo.

%PYTHON_CMD% fix_409_conflict.py

pause




