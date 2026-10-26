@echo off
REM boot.bat
REM Double-click this to launch EV.AI silently — no console window, same
REM as a normal Windows app. Calls venv\Scripts\pythonw.exe directly
REM (not "activate.bat" + a bare "python") so this always runs the
REM venv's own interpreter and packages, never whatever "python.exe"
REM happens to resolve to elsewhere in PATH.
REM
REM If EV.AI doesn't seem to start at all, use boot_debug.bat instead —
REM it keeps a console window open so you can actually see the error.
REM Once it's running, Settings -> View log also has everything EV.AI
REM has printed since startup, console or not.

cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo Could not find venv\Scripts\pythonw.exe
    echo Make sure this file is inside the EV_AI folder, next to main.py,
    echo and that you already ran: python -m venv venv
    pause
    exit /b 1
)

start "" "venv\Scripts\pythonw.exe" main.py
exit