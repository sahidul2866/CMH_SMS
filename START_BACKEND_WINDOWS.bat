@echo off
setlocal EnableExtensions
title CMH Smart Serial - Backend

if not defined CMH_WINDOWS_BACKEND_DIR goto :missing_configuration
if not defined CMH_WINDOWS_PYTHON goto :missing_configuration
if not defined CMH_WINDOWS_BACKEND_PORT goto :missing_configuration

cd /d "%CMH_WINDOWS_BACKEND_DIR%"
if errorlevel 1 goto :invalid_directory

"%CMH_WINDOWS_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %CMH_WINDOWS_BACKEND_PORT%
if errorlevel 1 goto :failed
exit /b 0

:missing_configuration
echo ERROR: Backend launcher configuration is missing.
goto :failed

:invalid_directory
echo ERROR: Cannot open backend directory: %CMH_WINDOWS_BACKEND_DIR%

:failed
echo.
echo Backend stopped. Review the error above.
pause
exit /b 1
