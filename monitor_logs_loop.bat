@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================================
echo  МОНИТОРИНГ ЛОГОВ RENDER В ЦИКЛЕ
echo ============================================================
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

if "%RENDER_OWNER_ID%"=="" (
    echo ⚠️  RENDER_OWNER_ID не установлен (опционально)
    echo    Будет получен автоматически
    echo.
)

echo.
echo 🔄 Запуск мониторинга логов...
echo    Обновление каждые 60 секунд
echo    Нажмите Ctrl+C для остановки
echo.

:loop
echo.
echo ============================================================
echo [%date% %time%] Получение логов...
echo ============================================================

curl -G ^
  -H "Authorization: Bearer %RENDER_API_KEY%" ^
  --data-urlencode "resource=%RENDER_SERVICE_ID%" ^
  --data-urlencode "limit=50" ^
  https://api.render.com/v1/logs

if defined RENDER_OWNER_ID (
    curl -G ^
      -H "Authorization: Bearer %RENDER_API_KEY%" ^
      --data-urlencode "ownerId=%RENDER_OWNER_ID%" ^
      --data-urlencode "resource=%RENDER_SERVICE_ID%" ^
      --data-urlencode "limit=50" ^
      https://api.render.com/v1/logs
)

echo.
echo ⏳ Ожидание 60 секунд до следующей проверки...
timeout /t 60 /nobreak >nul
goto loop



