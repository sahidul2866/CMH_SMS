@echo off
setlocal EnableExtensions EnableDelayedExpansion
title CMH Smart Serial - Windows Launcher

set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "FRONTEND_DIR=%PROJECT_DIR%frontend"
set "VENV_DIR=%BACKEND_DIR%\.venv"
set "SETUP_DIR=%PROJECT_DIR%.setup"
set "DATABASE_FILE=%BACKEND_DIR%\data\cmh_sms.db"
set "BACKEND_PORT=8100"
set "FRONTEND_PORT=4300"

echo.
echo ============================================================
echo   CMH Smart Serial - Complete Windows Setup and Launcher
echo ============================================================
echo.

if not exist "%BACKEND_DIR%\requirements.txt" goto :missing_project
if not exist "%FRONTEND_DIR%\package.json" goto :missing_project
if not exist "%SETUP_DIR%" mkdir "%SETUP_DIR%"

call :find_python
if not defined PYTHON_CMD call :install_python
if not defined PYTHON_CMD goto :python_failed

call :find_node
if not defined NPM_CMD call :install_node
if not defined NPM_CMD goto :node_failed

echo [1/8] Prerequisites ready.
call %PYTHON_CMD% --version
call "%NPM_CMD%" --version

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [2/8] Creating standalone Python environment...
    call %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :failed
) else (
    echo [2/8] Python environment already exists - skipping creation.
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

call :file_hash "%BACKEND_DIR%\requirements.txt" REQUIREMENTS_HASH
set "OLD_REQUIREMENTS_HASH="
if exist "%SETUP_DIR%\requirements.hash" set /p OLD_REQUIREMENTS_HASH=<"%SETUP_DIR%\requirements.hash"
if not "!REQUIREMENTS_HASH!"=="!OLD_REQUIREMENTS_HASH!" (
    echo [3/8] Installing or updating backend dependencies...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto :failed
    "%VENV_PYTHON%" -m pip install -r "%BACKEND_DIR%\requirements.txt"
    if errorlevel 1 goto :failed
    >"%SETUP_DIR%\requirements.hash" echo !REQUIREMENTS_HASH!
) else (
    echo [3/8] Backend dependencies are unchanged - skipping installation.
)

set "NEW_DATABASE=0"
if not exist "%DATABASE_FILE%" set "NEW_DATABASE=1"

echo [4/8] Checking database migrations...
pushd "%BACKEND_DIR%"
"%VENV_PYTHON%" -m alembic upgrade head
if errorlevel 1 (
    popd
    goto :failed
)

if "!NEW_DATABASE!"=="1" (
    echo       A new standalone database was created.
    "%VENV_PYTHON%" -m app.seed
    if errorlevel 1 (
        popd
        goto :failed
    )
    >"%SETUP_DIR%\database.seeded" echo Seeded on %DATE% %TIME%
) else if not exist "%SETUP_DIR%\database.seeded" (
    echo       Existing database found; loading missing baseline seed data once...
    "%VENV_PYTHON%" -m app.seed
    if errorlevel 1 (
        popd
        goto :failed
    )
    >"%SETUP_DIR%\database.seeded" echo Seeded on %DATE% %TIME%
) else (
    echo       Database already exists and is seeded - preserving its data.
)
popd

call :file_hash "%FRONTEND_DIR%\package-lock.json" FRONTEND_HASH
set "OLD_FRONTEND_HASH="
if exist "%SETUP_DIR%\frontend.hash" set /p OLD_FRONTEND_HASH=<"%SETUP_DIR%\frontend.hash"
if not exist "%FRONTEND_DIR%\node_modules" set "OLD_FRONTEND_HASH="
if not "!FRONTEND_HASH!"=="!OLD_FRONTEND_HASH!" (
    echo [5/8] Installing or updating frontend dependencies...
    pushd "%FRONTEND_DIR%"
    call "%NPM_CMD%" ci
    if errorlevel 1 (
        popd
        goto :failed
    )
    popd
    >"%SETUP_DIR%\frontend.hash" echo !FRONTEND_HASH!
) else (
    echo [5/8] Frontend dependencies are unchanged - skipping installation.
)

echo [6/8] Clearing application ports if required...
call :free_port %BACKEND_PORT%
call :free_port %FRONTEND_PORT%

echo [7/8] Starting CMH Smart Serial services...
set "CMH_WINDOWS_BACKEND_DIR=%BACKEND_DIR%"
set "CMH_WINDOWS_FRONTEND_DIR=%FRONTEND_DIR%"
set "CMH_WINDOWS_PYTHON=%VENV_PYTHON%"
set "CMH_WINDOWS_NPM=%NPM_CMD%"
set "CMH_WINDOWS_BACKEND_PORT=%BACKEND_PORT%"
set "CMH_WINDOWS_FRONTEND_PORT=%FRONTEND_PORT%"
start "CMH Smart Serial - Backend" "%PROJECT_DIR%START_BACKEND_WINDOWS.bat"
start "CMH Smart Serial - Frontend" "%PROJECT_DIR%START_FRONTEND_WINDOWS.bat"

echo [8/8] Waiting for the application to become ready...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%BACKEND_PORT%/api/v1/health' -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true;break} } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){exit 1}"
if errorlevel 1 (
    echo WARNING: Backend did not report ready within 60 seconds.
    echo Check the Backend window for an error.
) else (
    echo Backend is ready.
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%FRONTEND_PORT%' -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true;break} } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){exit 1}"
if errorlevel 1 (
    echo WARNING: Frontend did not report ready within 60 seconds.
    echo Check the Frontend window for an error.
) else (
    echo Frontend is ready.
    start "" "http://127.0.0.1:%FRONTEND_PORT%"
)

echo.
echo ============================================================
echo   CMH Smart Serial is running
echo   Application: http://127.0.0.1:%FRONTEND_PORT%
echo   API docs:    http://127.0.0.1:%BACKEND_PORT%/docs
echo ============================================================
echo.
echo Keep the Backend and Frontend windows open while using the app.
echo Close those windows or press Ctrl+C inside them to stop the app.
pause
exit /b 0

:find_python
set "PYTHON_CMD="
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if defined PYTHON_CMD exit /b 0
py -3.11 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.11"
if defined PYTHON_CMD exit /b 0
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=""%LocalAppData%\Programs\Python\Python312\python.exe"""
exit /b 0

:install_python
where winget >nul 2>&1 || exit /b 0
echo Python 3.12 was not found. Installing it with winget...
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --silent
call :find_python
exit /b 0

:find_node
set "NPM_CMD="
for /f "delims=" %%N in ('where npm.cmd 2^>nul') do if not defined NPM_CMD set "NPM_CMD=%%N"
if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
exit /b 0

:install_node
where winget >nul 2>&1 || exit /b 0
echo Node.js LTS was not found. Installing it with winget...
winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements --silent
if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
exit /b 0

:file_hash
set "%~2="
if not exist "%~1" exit /b 0
for /f "usebackq delims=" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%~1').Hash"`) do set "%~2=%%H"
exit /b 0

:free_port
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -State Listen -LocalPort %~1 -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique"`) do (
    echo       Port %~1 is used by PID %%P. Stopping it...
    taskkill /PID %%P /T /F >nul 2>&1
)
exit /b 0

:missing_project
echo ERROR: backend or frontend project files are missing.
echo Place this BAT file in the root CMH_SMS folder and run it again.
goto :failed

:python_failed
echo ERROR: Python 3.11 or newer could not be installed or detected.
echo Install Python 3.12 from https://www.python.org/downloads/windows/
echo Enable the Python Launcher during installation, then run this file again.
goto :failed

:node_failed
echo ERROR: Node.js LTS could not be installed or detected.
echo Install it from https://nodejs.org/ and run this file again.
goto :failed

:failed
echo.
echo SETUP FAILED. Read the error above, correct it, and run this file again.
echo Completed steps will be detected and skipped automatically.
pause
exit /b 1
