@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cls
echo ============================================================
echo  🔍 ПРОВЕРКА ДУБЛИРУЮЩИХ СЕРВИСОВ В RENDER
echo ============================================================
echo.
echo  Этот скрипт проверяет, нет ли нескольких сервисов
echo  в Render с одним и тем же токеном Telegram бота.
echo.
echo  Это поможет найти причину 409 Conflict.
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

REM Проверка переменных окружения
if "%RENDER_API_KEY%"=="" (
    echo Please set RENDER_API_KEY environment variable
    echo Usage: set RENDER_API_KEY=your_api_key_here
    exit /b 2
)
echo.
echo 🚀 Запуск проверки...
echo.

%PYTHON_CMD% check_duplicate_services.py

pause







