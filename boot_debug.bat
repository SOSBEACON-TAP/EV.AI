@echo off
REM boot_debug.bat
REM Same as boot.bat, but keeps a console window open and shows EV.AI's
REM own console output — use this one if boot.bat doesn't seem to start
REM anything, or if EV.AI closes right away and you need to see why.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Could not find venv\Scripts\python.exe
    echo Make sure this file is inside the EV_AI folder, next to main.py,
    echo and that you already ran: python -m venv venv
    pause
    exit /b 1
)

venv\Scripts\python.exe main.py

if errorlevel 1 (
    echo.
    echo EV.AI closed with an error - see above.
    pause
)
