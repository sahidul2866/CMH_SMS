@echo off
setlocal EnableExtensions EnableDelayedExpansion
title CMH Smart Serial - Windows Launcher

set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "FRONTEND_DIR=%PROJECT_DIR%frontend"
set "VENV_DIR=%BACKEND_DIR%\.venv"
set "SETUP_DIR=%PROJECT_DIR%.setup"
set "WINDOWS_ENV=%SETUP_DIR%\windows.env.bat"
set "DATABASE_FILE=%BACKEND_DIR%\data\cmh_sms.db"
set "BACKEND_PORT=8100"

echo.
echo ============================================================
echo   CMH Smart Serial - Complete Windows Setup and Launcher
echo ============================================================
echo.

if not exist "%BACKEND_DIR%\requirements.txt" goto :missing_project
if not exist "%FRONTEND_DIR%\package.json" goto :missing_project
if not exist "%SETUP_DIR%" mkdir "%SETUP_DIR%"

set "PYTHON_CMD=%CMH_SMS_PYTHON_CMD%"
if not defined PYTHON_CMD call :find_python
if not defined PYTHON_CMD call :install_python
if not defined PYTHON_CMD goto :python_failed

call :find_espeak
if not defined ESPEAK_EXE call :install_espeak

echo [1/9] Prerequisites ready.
echo Selected Python command: !PYTHON_CMD!
call %PYTHON_CMD% --version
if defined ESPEAK_EXE (
    echo eSpeak NG: !ESPEAK_EXE!
) else (
    echo INFO: eSpeak NG is unavailable. It is only the basic emergency voice.
    echo       The natural offline Bengali neural voice will be installed below.
)

call :ensure_windows_config
if not defined CMH_SMS_ADMIN_PASSWORD goto :failed

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [2/9] Creating standalone Python environment...
    call %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto :failed
) else (
    echo [2/9] Python environment already exists - skipping creation.
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

call :file_hash "%BACKEND_DIR%\requirements.txt" REQUIREMENTS_HASH
set "OLD_REQUIREMENTS_HASH="
if exist "%SETUP_DIR%\requirements.hash" set /p OLD_REQUIREMENTS_HASH=<"%SETUP_DIR%\requirements.hash"
if not "!REQUIREMENTS_HASH!"=="!OLD_REQUIREMENTS_HASH!" (
    echo [3/9] Installing or updating backend dependencies...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto :failed
    "%VENV_PYTHON%" -m pip install -r "%BACKEND_DIR%\requirements.txt"
    if errorlevel 1 goto :failed
    >"%SETUP_DIR%\requirements.hash" echo !REQUIREMENTS_HASH!
) else (
    echo [3/9] Backend dependencies are unchanged - skipping installation.
)

if not exist "%BACKEND_DIR%\data\models\mms-tts-ben\model.safetensors" (
    echo       Installing the natural offline Bengali neural voice runtime...
    "%VENV_PYTHON%" -m pip install -r "%BACKEND_DIR%\requirements-windows-audio.txt"
    if errorlevel 1 (
        echo WARNING: Offline neural voice runtime installation failed.
    ) else (
        echo       Downloading the Meta MMS Bengali model for permanent offline use...
        "%VENV_PYTHON%" -c "from huggingface_hub import snapshot_download; snapshot_download('facebook/mms-tts-ben', local_dir=r'%BACKEND_DIR%\data\models\mms-tts-ben')"
        if errorlevel 1 echo WARNING: Offline neural model download failed; rerun when internet is available.
    )
) else (
    echo       Natural offline Bengali neural voice is already installed.
)

set "NEW_DATABASE=0"
if not exist "%DATABASE_FILE%" set "NEW_DATABASE=1"

echo [4/9] Checking database migrations...
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

if not exist "%FRONTEND_DIR%\dist\cmh-smart-serial\browser\index.html" if not exist "%FRONTEND_DIR%\dist\cmh-smart-serial\index.html" goto :frontend_missing
echo [5/9] Prebuilt frontend is included - no Node.js installation required.
echo [6/9] Frontend is ready for server hosting.

echo       Checking the application port...
call :free_port %BACKEND_PORT%
if errorlevel 1 goto :failed

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object {$_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'} ^| Sort-Object InterfaceMetric ^| Select-Object -First 1 -ExpandProperty IPAddress); if($ip){$ip}else{'SERVER-PC-IP'}"`) do set "LAN_IP=%%I"
set "CMH_SMS_ALLOWED_HOSTS=localhost,127.0.0.1"
if not "!LAN_IP!"=="SERVER-PC-IP" set "CMH_SMS_ALLOWED_HOSTS=!CMH_SMS_ALLOWED_HOSTS!,!LAN_IP!"

echo [7/9] Configuring Windows Firewall for the hospital LAN...
netsh advfirewall firewall show rule name="CMH Smart Serial 8100" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="CMH Smart Serial 8100" dir=in action=allow protocol=TCP localport=%BACKEND_PORT% profile=private >nul 2>&1
    if errorlevel 1 echo WARNING: Run this launcher once as Administrator to add the private-network firewall rule.
) else (
    echo       Firewall rule already exists.
)

echo [8/9] Starting the LAN-visible CMH Smart Serial server...
set "CMH_WINDOWS_BACKEND_DIR=%BACKEND_DIR%"
set "CMH_WINDOWS_PYTHON=%VENV_PYTHON%"
set "CMH_WINDOWS_BACKEND_PORT=%BACKEND_PORT%"
start "CMH Smart Serial - Server" "%PROJECT_DIR%START_BACKEND_WINDOWS.bat"

echo [9/9] Waiting for the application to become ready...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:%BACKEND_PORT%/api/v1/health' -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true;break} } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){exit 1}"
if errorlevel 1 (
    echo WARNING: Backend did not report ready within 60 seconds.
    echo Check the Backend window for an error.
) else (
    echo Backend is ready.
)

start "" "http://127.0.0.1:%BACKEND_PORT%"

echo.
echo ============================================================
echo   CMH Smart Serial is running
echo   Server:      http://127.0.0.1:%BACKEND_PORT%
echo   LAN clients: http://%LAN_IP%:%BACKEND_PORT%
echo   API docs:    http://127.0.0.1:%BACKEND_PORT%/docs
echo ============================================================
echo.
echo Connect every radiographer PC and this server to the same wired switch.
echo Keep the Server window open while using the app.
pause
exit /b 0

:find_python
set "PYTHON_CMD="
python -c "import sys; raise SystemExit(sys.version_info[:2] not in [(3,11),(3,12),(3,13),(3,14)])" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if defined PYTHON_CMD exit /b 0
py -3.14 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.14"
if defined PYTHON_CMD exit /b 0
py -3.13 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.13"
if defined PYTHON_CMD exit /b 0
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if defined PYTHON_CMD exit /b 0
py -3.11 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.11"
if defined PYTHON_CMD exit /b 0
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYTHON_CMD=""%LocalAppData%\Programs\Python\Python313\python.exe"""
if defined PYTHON_CMD exit /b 0
if exist "%ProgramFiles%\Python313\python.exe" set "PYTHON_CMD=""%ProgramFiles%\Python313\python.exe"""
exit /b 0

:install_python
where winget >nul 2>&1 || exit /b 0
echo Python 3.12 was not found. Installing it with winget...
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --silent
call :find_python
exit /b 0

:find_node
set "NPM_CMD="
set "NODE_EXE="
for /f "delims=" %%N in ('where node.exe 2^>nul') do if not defined NODE_EXE set "NODE_EXE=%%N"
if defined NODE_EXE for %%N in ("!NODE_EXE!") do call :accept_npm "%%~dpNnpm.cmd"
call :accept_npm "%ProgramFiles%\nodejs\npm.cmd"
for /f "delims=" %%N in ('where npm.cmd 2^>nul') do call :accept_npm "%%N"
exit /b 0

:accept_npm
if defined NPM_CMD exit /b 0
if not exist "%~1" exit /b 0
call "%~1" --version >nul 2>&1
if not errorlevel 1 set "NPM_CMD=%~1"
exit /b 0

:install_node
where winget >nul 2>&1 || exit /b 0
echo Node.js LTS was not found. Installing it with winget...
winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements --silent
call :find_node
exit /b 0

:ensure_windows_config
set "CMH_SMS_ADMIN_PASSWORD="
if exist "%WINDOWS_ENV%" call "%WINDOWS_ENV%"
if defined CMH_SMS_ADMIN_PASSWORD if not "!CMH_SMS_ADMIN_PASSWORD:~9,1!"=="" exit /b 0
echo Creating or repairing the Windows server configuration...
set "INITIAL_ADMIN_PASSWORD="
for /f "delims=" %%P in ('%PYTHON_CMD% -c "import secrets;print(secrets.token_hex(10))"') do set "INITIAL_ADMIN_PASSWORD=%%P"
if "!INITIAL_ADMIN_PASSWORD:~9,1!"=="" exit /b 1
>"%WINDOWS_ENV%" echo @echo off
>>"%WINDOWS_ENV%" echo set "CMH_SMS_ADMIN_USERNAME=admin"
>>"%WINDOWS_ENV%" echo set "CMH_SMS_ADMIN_PASSWORD=!INITIAL_ADMIN_PASSWORD!"
>>"%WINDOWS_ENV%" echo set "CMH_SMS_AUDIO_ENABLED=true"
>>"%WINDOWS_ENV%" echo set "CMH_SMS_ENVIRONMENT=development"
>>"%WINDOWS_ENV%" echo set "CMH_SMS_PUBLIC_HTTPS=false"
>>"%WINDOWS_ENV%" echo set "CMH_SMS_COOKIE_SECURE=false"
>"%SETUP_DIR%\INITIAL_ADMIN_LOGIN.txt" echo Username: admin
>>"%SETUP_DIR%\INITIAL_ADMIN_LOGIN.txt" echo Initial password: !INITIAL_ADMIN_PASSWORD!
set "CMH_SMS_ADMIN_USERNAME=admin"
set "CMH_SMS_ADMIN_PASSWORD=!INITIAL_ADMIN_PASSWORD!"
echo.
echo IMPORTANT - initial administrator login:
echo Username: admin
echo Password: !INITIAL_ADMIN_PASSWORD!
echo Also saved in .setup\INITIAL_ADMIN_LOGIN.txt
echo.
exit /b 0

:find_espeak
set "ESPEAK_EXE="
for /f "delims=" %%E in ('where espeak-ng.exe 2^>nul') do if not defined ESPEAK_EXE set "ESPEAK_EXE=%%E"
if exist "%ProgramFiles%\eSpeak NG\espeak-ng.exe" set "ESPEAK_EXE=%ProgramFiles%\eSpeak NG\espeak-ng.exe"
if exist "%ProgramFiles(x86)%\eSpeak NG\espeak-ng.exe" set "ESPEAK_EXE=%ProgramFiles(x86)%\eSpeak NG\espeak-ng.exe"
exit /b 0

:install_espeak
where winget >nul 2>&1 || exit /b 0
echo eSpeak NG was not found. Installing the Windows offline voice...
winget install --id eSpeak-NG.eSpeak-NG -e --accept-package-agreements --accept-source-agreements --silent
call :find_espeak
exit /b 0

:file_hash
set "%~2="
if not exist "%~1" exit /b 0
for /f "usebackq delims=" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%~1').Hash"`) do set "%~2=%%H"
exit /b 0

:free_port
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -State Listen -LocalPort %~1 -ErrorAction SilentlyContinue ^| Select-Object -ExpandProperty OwningProcess -Unique"`) do (
    echo ERROR: Port %~1 is already used by PID %%P.
    echo Stop the existing service explicitly, then run this launcher again.
    exit /b 1
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

:frontend_missing
echo ERROR: The prebuilt frontend is missing from this package.
echo Download and extract the latest CMH_SMS_Windows.zip, then run again.
goto :failed

:failed
echo.
echo SETUP FAILED. Read the error above, correct it, and run this file again.
echo Completed steps will be detected and skipped automatically.
pause
exit /b 1
