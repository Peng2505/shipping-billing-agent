@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Shipping Billing AI - Install

echo === 1_Install (Windows) ===
echo Project: %CD%
echo.

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,11) else 1)" 2>nul
  if errorlevel 1 (
    echo ERROR: Need Python 3.11+. Install from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  py -3 "scripts\quick_start\install_env.py"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    pause
    exit /b 1
  )
  python "scripts\quick_start\install_env.py"
)

set ERR=%ERRORLEVEL%
echo.
if not %ERR%==0 (
  echo Install failed with code %ERR%.
  pause
  exit /b %ERR%
)
echo Done. Next: edit .env then double-click 2_Start.bat
pause
exit /b 0
