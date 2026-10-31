@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Shipping Billing AI - Start

echo === 2_Start (Windows) ===
echo Project: %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv missing. Run 1_Install.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -u "scripts\demo\start_exam.py"
set ERR=%ERRORLEVEL%
echo.
if not %ERR%==0 (
  echo Start failed with code %ERR%.
  pause
  exit /b %ERR%
)
echo.
echo UI: http://localhost:8501
echo Stop later with 3_Stop.bat
pause
exit /b 0
