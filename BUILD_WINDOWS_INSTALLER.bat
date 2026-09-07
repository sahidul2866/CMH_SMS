@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Build CMH Smart Serial Windows Installer

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "BUILD_VENV=%ROOT%.installer-venv"
set "MODEL=%BACKEND%\data\models\mms-tts-ben\model.safetensors"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

where python >nul 2>&1 || goto :python_missing
if not exist "%BUILD_VENV%\Scripts\python.exe" python -m venv "%BUILD_VENV%"
if errorlevel 1 goto :failed
set "PYTHON=%BUILD_VENV%\Scripts\python.exe"

echo [1/6] Installing reproducible build and application dependencies...
"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r "%BACKEND%\requirements.txt" -r "%BACKEND%\requirements-windows-audio.txt" -r "%BACKEND%\requirements-windows-build.txt"
if errorlevel 1 goto :failed

echo [2/6] Checking the prebuilt frontend...
if not exist "%ROOT%frontend\dist\cmh-smart-serial\browser\index.html" goto :frontend_missing

echo [3/6] Downloading the offline Bengali model when needed...
if not exist "%MODEL%" "%PYTHON%" -c "from huggingface_hub import snapshot_download; snapshot_download('facebook/mms-tts-ben', local_dir=r'%BACKEND%\data\models\mms-tts-ben')"
if errorlevel 1 goto :failed

echo [4/6] Freezing FastAPI, Python, frontend and voice model...
pushd "%ROOT%"
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath "%ROOT%packaging-dist" --workpath "%ROOT%packaging-build" "%ROOT%packaging\windows\cmh-smart-serial.spec"
if errorlevel 1 (
    popd
    goto :failed
)
popd

echo [5/6] Installing Inno Setup compiler when needed...
if not exist "%ISCC%" winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements --silent
if not exist "%ISCC%" goto :inno_missing

echo [6/6] Creating the one-file hospital installer...
"%ISCC%" /DSourceRoot="%ROOT:~0,-1%" "%ROOT%packaging\windows\CMHSmartSerial.iss"
if errorlevel 1 goto :failed

echo.
echo Installer created successfully:
echo %ROOT%installer-output\CMH-Smart-Serial-Setup.exe
pause
exit /b 0

:python_missing
echo ERROR: Python is required only on this Windows build PC.
goto :failed
:frontend_missing
echo ERROR: The prebuilt frontend is missing. Use the latest project package.
goto :failed
:inno_missing
echo ERROR: Inno Setup 6 could not be installed or detected.
goto :failed
:failed
echo.
echo INSTALLER BUILD FAILED. Correct the error above and run this file again.
pause
exit /b 1
