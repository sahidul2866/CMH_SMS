@echo off
setlocal EnableExtensions
title Install CMH Smart Serial Automatic Startup

set "PROJECT_DIR=%~dp0"
set "SERVER_SCRIPT=%PROJECT_DIR%START_CMH_FOREVER_WINDOWS.bat"
set "TASK_NAME=CMH Smart Serial Server"

if not exist "%PROJECT_DIR%.setup\windows.env.bat" goto :not_installed
if not exist "%PROJECT_DIR%backend\.venv\Scripts\python.exe" goto :not_installed

echo Installing automatic startup for the current Windows user...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\install_source_autostart.ps1"
if errorlevel 1 goto :failed

powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1

echo.
echo Automatic startup installed successfully.
echo The server starts whenever this Windows user signs in and restarts after a crash.
echo Keep this user signed in so Windows can play announcements through the speakers.
echo To remove it later, run UNINSTALL_AUTOSTART_WINDOWS.bat.
pause
exit /b 0

:not_installed
echo Run RUN_WINDOWS.bat once before installing automatic startup.
goto :failed

:failed
echo.
echo Automatic startup installation failed. Right-click this file and choose
echo Run as administrator, then try again.
pause
exit /b 1
