@echo off
chcp 65001 >nul
echo ==========================================
echo    Work Manager
echo ==========================================
echo Starting...
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Make sure Python and dependencies are installed.
    echo Run: pip install PyQt6 matplotlib pywin32 psutil
    pause
)
