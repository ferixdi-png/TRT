@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cls
echo ============================================================
echo  🛡️  БЕЗОПАСНАЯ СИСТЕМА АВТОМАТИЧЕСКОГО ИСПРАВЛЕНИЯ
echo ============================================================
echo.
echo  Все правила безопасности учтены:
echo  ✅ Фиксит ТОЛЬКО после деплоя
echo  ✅ Фильтрует логи по времени
echo  ✅ Ошибка должна повториться ≥2 раз
echo  ✅ Один тип ошибки = один фикс
echo  ✅ Grace-период 60 сек после деплоя
echo  ✅ Throttle: ≤3 фикса в час
echo  ✅ Проверка git status перед патчем
echo  ✅ Минимальный diff
echo  ✅ Проверка компиляции
echo  ✅ Whitelist файлов
echo  ✅ State-файл для отслеживания
echo  ✅ Идемпотентность
echo  ✅ Проверка результата после деплоя
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
echo 🚀 Запуск безопасной системы...
echo.

%PYTHON_CMD% auto_fix_complete_safe.py

pause







