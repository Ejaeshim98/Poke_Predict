@echo off
setlocal

cd /d "%~dp0"

echo ======================================
echo   Poke Predict - Starting Application
echo ======================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -3 -m venv .venv 2>nul
  if errorlevel 1 (
    python -m venv .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Could not find a usable Python installation.
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  echo Then run this launcher again.
  pause
  exit /b 1
)

echo Installing/updating app dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  echo Check your internet connection and try again.
  pause
  exit /b 1
)

echo.
echo Opening app in your browser...
start "" "http://localhost:8501"

echo Starting server (leave this window open while app is running)...
".venv\Scripts\python.exe" run_app.py

echo.
echo App closed.
pause
