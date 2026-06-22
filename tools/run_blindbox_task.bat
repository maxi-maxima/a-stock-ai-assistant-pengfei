@echo off
setlocal
cd /d "C:\Users\1\Desktop\KIMIstock\gemini"
set PYTHONIOENCODING=utf-8
"C:\Users\1\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\1\Desktop\KIMIstock\gemini\tools\blindbox_daily_runner.py" --once >> "C:\Users\1\Desktop\KIMIstock\gemini\logs\blindbox_task.log" 2>&1
endlocal
