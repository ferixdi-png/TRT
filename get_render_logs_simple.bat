@echo off
chcp 65001 >nul
echo ============================================================
echo  ПОЛУЧЕНИЕ ЛОГОВ С RENDER
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
    echo 💡 Установите API ключ:
    echo    set RENDER_API_KEY=your_api_key_here
    echo.
    echo 📋 Как получить API ключ:
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
    set /p RENDER_SERVICE_ID="Введите ваш RENDER_SERVICE_ID: "
    if "!RENDER_SERVICE_ID!"=="" (
        echo ❌ Service ID обязателен!
        pause
        exit /b 1
    )
)

echo.
echo 📊 Получение логов...
echo.

%PYTHON_CMD% get_render_logs.py --service-id %RENDER_SERVICE_ID% --lines 200 --analyze

echo.
echo ============================================================
pause


