@echo off
REM Настройка автоматического push в GitHub
REM ВАЖНО: Установите GITHUB_TOKEN в переменную окружения перед запуском!

cd /d "%~dp0\.."

REM Проверяем наличие токена
if "%GITHUB_TOKEN%"=="" (
    echo ❌ GITHUB_TOKEN not set!
    echo.
    echo Установите токен:
    echo   set GITHUB_TOKEN=your_token_here
    echo.
    echo Или создайте файл .github_token в корне проекта
    exit /b 1
)

REM Настраиваем git remote
git remote set-url origin https://%GITHUB_TOKEN%@github.com/ferixdi-png/5656.git

echo ✅ Git remote configured with token
echo.
echo Теперь можно использовать:
echo   python scripts/auto_push.py
echo или
echo   python scripts/auto_push.py --message "Your commit message"

