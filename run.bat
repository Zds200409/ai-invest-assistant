@echo off
cd /d "%~dp0"

set PY=python
where python >nul 2>nul
if errorlevel 1 set PY=E:\Python\python.exe

echo ============================================================
echo   AI Investment Research Assistant
echo ============================================================
echo.
echo   1) Keep this window OPEN while using the app
echo   2) Open browser at:  http://127.0.0.1:8000
echo   3) Stop the service: press Ctrl+C, or close this window
echo.
echo   Model config: edit the .env file in this folder
echo ============================================================
echo.

"%PY%" app.py

echo.
echo ------------------------------------------------------------
echo Service stopped.
if errorlevel 1 (
  echo [ERROR] Startup failed - please read the message above.
)
echo ------------------------------------------------------------
pause
