@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found. Please install Python 3.9+ first.
  pause
  exit /b 1
)

set "VENV=%ROOT%\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"
set "REQ=%ROOT%requirements.txt"
set "HASH_FILE=%VENV%\req.hash"

if not exist "%PY%" (
  echo Creating virtual environment...
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
  )
)

for /f "delims=" %%H in ('"%PY%" -c "import hashlib, pathlib; p=pathlib.Path(r'%REQ%'); print(hashlib.sha256(p.read_bytes()).hexdigest())"') do set "REQ_HASH=%%H"

set "NEED_INSTALL=0"
if not exist "%HASH_FILE%" set "NEED_INSTALL=1"
if exist "%HASH_FILE%" (
  set /p OLD_HASH=<"%HASH_FILE%"
  if /I not "%OLD_HASH%"=="%REQ_HASH%" set "NEED_INSTALL=1"
)
if /I "%FORCE_INSTALL%"=="1" set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="1" (
  echo Installing dependencies...
  "%PIP%" install -r "%REQ%"
  if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
  )
  echo %REQ_HASH%>"%HASH_FILE%"
) else (
  echo Dependencies are up to date.
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

"%PY%" -m streamlit run dashboard.py
