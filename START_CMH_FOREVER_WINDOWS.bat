@echo off
setlocal EnableExtensions EnableDelayedExpansion
title CMH Smart Serial - Always On Server

set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "VENV_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "WINDOWS_ENV=%PROJECT_DIR%.setup\windows.env.bat"
set "BACKEND_PORT=8100"

if not exist "%VENV_PYTHON%" goto :not_installed
if not exist "%WINDOWS_ENV%" goto :not_installed
if not exist "%PROJECT_DIR%frontend\dist\cmh-smart-serial\browser\index.html" if not exist "%PROJECT_DIR%frontend\dist\cmh-smart-serial\index.html" goto :not_installed

call "%WINDOWS_ENV%"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object {$_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'} ^| Sort-Object InterfaceMetric ^| Select-Object -First 1 -ExpandProperty IPAddress); if($ip){$ip}else{''}"`) do set "LAN_IP=%%I"
set "CMH_SMS_ALLOWED_HOSTS=localhost,127.0.0.1"
if defined LAN_IP set "CMH_SMS_ALLOWED_HOSTS=!CMH_SMS_ALLOWED_HOSTS!,!LAN_IP!"

:run
echo [%DATE% %TIME%] Starting CMH Smart Serial...
pushd "%BACKEND_DIR%"
"%VENV_PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --no-access-log
set "SERVER_EXIT=!ERRORLEVEL!"
popd
echo [%DATE% %TIME%] Server exited with code !SERVER_EXIT!; restarting in 10 seconds.
timeout /t 10 /nobreak >nul
goto :run

:not_installed
echo CMH Smart Serial has not been installed yet.
echo Run RUN_WINDOWS.bat first, then install automatic startup again.
pause
exit /b 1
