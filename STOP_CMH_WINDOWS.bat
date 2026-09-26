@echo off
setlocal EnableExtensions
rem Disable first so the watchdog cannot undo an intentional maintenance stop.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Disable-ScheduledTask -TaskName 'CMH Smart Serial Server' | Out-Null; Stop-ScheduledTask -TaskName 'CMH Smart Serial Server'"
if errorlevel 1 (
    echo ERROR: Could not stop automatic recovery. Run as Administrator and try again.
    pause
    exit /b 1
)
echo CMH stopped and automatic recovery disabled for maintenance.
echo Run RUN_WINDOWS.bat or INSTALL_AUTOSTART_WINDOWS.bat to enable it again.
pause
exit /b 0
