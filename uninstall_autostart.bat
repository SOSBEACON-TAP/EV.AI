@echo off
REM uninstall_autostart.bat
REM Removes the Startup-folder shortcut created by install_autostart.bat,
REM so EV AI stops launching automatically at Windows login.

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EV_AI.lnk"

if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo EV AI will no longer start automatically at login.
) else (
    echo No auto-start shortcut was found - nothing to remove.
)
pause
