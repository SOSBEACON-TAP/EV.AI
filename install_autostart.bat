@echo off
REM install_autostart.bat
REM Run this ONCE. It creates a shortcut to boot.bat in your Windows
REM Startup folder, so EV AI launches automatically every time you log
REM into Windows — no manual double-click needed.
REM
REM IMPORTANT: this only runs EV AI once Windows has actually booted and
REM you've logged in. Nothing can run while the PC is fully powered off —
REM but by the time your desktop appears, EV AI will already be starting.
REM
REM Place this file in the same folder as boot.bat before running it.

setlocal
set "SCRIPT_DIR=%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\EV_AI.lnk"

if not exist "%SCRIPT_DIR%boot.bat" (
    echo Could not find boot.bat next to this script.
    echo Make sure install_autostart.bat is in your EV_AI folder.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell;" ^
    "$Shortcut = $WshShell.CreateShortcut('%SHORTCUT%');" ^
    "$Shortcut.TargetPath = '%SCRIPT_DIR%boot.bat';" ^
    "$Shortcut.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$Shortcut.WindowStyle = 7;" ^
    "$Shortcut.Description = 'Launch EV AI';" ^
    "$Shortcut.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo Success! EV AI will now start automatically whenever you log into Windows.
    echo To undo this later, run uninstall_autostart.bat.
) else (
    echo.
    echo Something went wrong - the shortcut was not created.
)
pause
