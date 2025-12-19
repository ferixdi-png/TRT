@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================================
echo  🤖 ИНТЕГРАЦИЯ С CURSOR ДЛЯ АВТОМАТИЧЕСКОГО ИСПРАВЛЕНИЯ
echo ============================================================
echo.
echo  Этот скрипт будет:
echo  ✅ Мониторить логи на Render
echo  ✅ Находить ошибки
echo  ✅ Создавать задачи для Cursor AI
echo  ✅ Сохранять промпты для автоматического исправления
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

REM Установка переменных окружения (если не установлены)
if "%RENDER_API_KEY%"=="" (
    set RENDER_API_KEY=rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw
)

if "%RENDER_SERVICE_ID%"=="" (
    set RENDER_SERVICE_ID=srv-d4s025er433s73bsf62g
)

if "%TELEGRAM_BOT_TOKEN%"=="" (
    set TELEGRAM_BOT_TOKEN=8524869517:AAEqLyZ3guOUoNsAnmkkKTTX56MoKW2f30Y
)

echo ✅ Переменные окружения установлены
echo.
echo 🚀 Запуск интеграции с Cursor...
echo.

%PYTHON_CMD% cursor_auto_fix.py

pause

