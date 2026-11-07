@echo off
setlocal enabledelayedexpansion

REM ====== SETTINGS ======
set SCRIPT_NAME=RV.py
set EXE_NAME=RV
REM ======================

echo.
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found in PATH.
  echo Install Python from python.org, then re-run this.
  pause
  exit /b 1
)

echo.
echo [2/5] Creating venv if needed...
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create .venv
    pause
    exit /b 1
  )
)

echo.
echo [3/5] Installing/Updating PyInstaller...
call .\.venv\Scripts\python.exe -m pip install --upgrade pip
call .\.venv\Scripts\python.exe -m pip install pyinstaller

echo.
echo [4/5] Building EXE...
call .\.venv\Scripts\python.exe -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%EXE_NAME%" ^
  "%SCRIPT_NAME%"

if errorlevel 1 (
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)

echo.
echo [5/5] Done!
echo Your EXE is here:
echo   %cd%\dist\%EXE_NAME%.exe
echo.
pause
endlocal
