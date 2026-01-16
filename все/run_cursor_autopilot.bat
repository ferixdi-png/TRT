@echo off
echo ====== Запуск Cursor Autopilot ======
:loop
echo Запуск Cursor Agent...
cursor agent --project "C:\Users\User\Desktop\5656-main" --mode loop --instructions "C:\Users\User\Desktop\5656-main\ai_instructions.txt"
echo Cursor упал или завершил работу. Перезапуск через 5 секунд...
timeout /t 5
goto loop
