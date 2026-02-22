@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PY=%ROOT%\.venv\Scripts\python.exe"

if exist "%PY%" (
  "%PY%" tools\clear_keys.py
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found. Please install Python first.
    pause
    exit /b 1
  )
  python tools\clear_keys.py
)

echo Done.
pause
