@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title Shipping Billing AI - Stop

echo === 3_Stop (Windows) ===
echo Project: %CD%
echo.

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -u "scripts\demo\stop_exam.py"
) else (
  echo WARNING: .venv missing; trying system python
  python -u "scripts\demo\stop_exam.py" 2>nul
)

echo.
echo Stopped this project's Streamlit / LocalTunnel session ^(if running^).
pause
exit /b 0
