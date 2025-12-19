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

REM Установка переменных окружения (fallback)
set RENDER_API_KEY=rnd_nXYNUy1lrWO4QTIjVMYizzKyHItw

echo ✅ Переменные окружения установлены (fallback)
echo.
echo 🚀 Запуск проверки...
echo.

%PYTHON_CMD% check_duplicate_services.py

pause



