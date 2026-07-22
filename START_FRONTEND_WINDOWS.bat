@echo off
setlocal EnableExtensions
title CMH Smart Serial - Frontend

if not defined CMH_WINDOWS_FRONTEND_DIR goto :missing_configuration
if not defined CMH_WINDOWS_NPM goto :missing_configuration
if not defined CMH_WINDOWS_FRONTEND_PORT goto :missing_configuration

cd /d "%CMH_WINDOWS_FRONTEND_DIR%"
if errorlevel 1 goto :invalid_directory

call "%CMH_WINDOWS_NPM%" start -- --host 127.0.0.1 --port %CMH_WINDOWS_FRONTEND_PORT%
if errorlevel 1 goto :failed
exit /b 0

:missing_configuration
echo ERROR: Frontend launcher configuration is missing.
goto :failed

:invalid_directory
echo ERROR: Cannot open frontend directory: %CMH_WINDOWS_FRONTEND_DIR%

:failed
echo.
echo Frontend stopped. Review the error above.
pause
exit /b 1
