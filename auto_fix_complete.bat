@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cls
echo ============================================================
echo  🤖 ПОЛНОСТЬЮ АВТОМАТИЗИРОВАННАЯ СИСТЕМА ИСПРАВЛЕНИЯ
echo ============================================================
echo.
echo  Этот скрипт:
echo  ✅ Проверяет статус деплоя на Render
echo  ✅ Ждёт завершения деплоя перед проверкой ошибок
echo  ✅ Автоматически исправляет найденные ошибки
echo  ✅ Коммитит и пушит изменения в GitHub
echo  ✅ Ждёт завершения деплоя после исправлений
echo  ✅ Показывает понятный вывод всех действий
echo.
echo  ВСЁ В ОДНОМ ОКНЕ - НИЧЕГО ДОПОЛНИТЕЛЬНО НЕ НУЖНО!
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
    if %errorlevel% neq 0 (
        echo ❌ Ошибка при установке requests
        pause
        exit /b 1
    )
)

echo ✅ Все зависимости установлены
echo.

REM Проверка переменных окружения
if "%RENDER_API_KEY%"=="" (
    echo Please set RENDER_API_KEY environment variable
    exit /b 2
)
if "%RENDER_SERVICE_ID%"=="" (
    echo Please set RENDER_SERVICE_ID environment variable
    exit /b 2
)
if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo Please set TELEGRAM_BOT_TOKEN environment variable
    exit /b 2
)

echo ✅ Переменные окружения установлены
echo.
echo 🚀 Запуск полностью автоматизированной системы...
echo.

%PYTHON_CMD% auto_fix_complete.py

pause







