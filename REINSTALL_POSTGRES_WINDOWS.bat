@echo off
setlocal DisableDelayedExpansion
title CMH - Reinstall PostgreSQL 17
set "CMH_RESET_SCRIPT=%~f0"
set "CMH_RESET_ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$raw = Get-Content -LiteralPath $env:CMH_RESET_SCRIPT -Raw; $marker = '# POWERSHELL_' + 'PAYLOAD'; & ([scriptblock]::Create($raw.Substring($raw.IndexOf($marker) + $marker.Length)))"
if errorlevel 1 (
    echo.
    echo Reinstallation stopped. Read the error above. Do not start CMH until PostgreSQL is ready.
    pause
    exit /b 1
)
rem Ignore any obsolete database URL inherited by this CMD session.
set "CMH_SMS_DATABASE_URL="
call "%~dp0RUN_WINDOWS.bat"
exit /b %ERRORLEVEL%
# POWERSHELL_PAYLOAD
$ErrorActionPreference = 'Stop'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Right-click this BAT and choose Run as administrator.'
    }
    $root = $env:CMH_RESET_ROOT
    if (-not (Test-Path -LiteralPath (Join-Path $root 'RUN_WINDOWS.bat'))) {
        throw 'Place this file inside the CMH_SMS project folder beside RUN_WINDOWS.bat.'
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install or update App Installer from Microsoft Store first (winget is required). Nothing was removed.'
    }
    $serviceName = 'postgresql-x64-17'
    $target = Join-Path $env:ProgramFiles 'PostgreSQL\17'
    $other = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Where-Object Name -ne $serviceName)
    if ($other.Count) { throw 'Other PostgreSQL services exist. This reset is only for the single PostgreSQL 17 CMH installation. Nothing was removed.' }
    $service = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
    if ($service -and $service.PathName -notlike ('*' + $target + '\*')) {
        throw 'PostgreSQL uses a custom installation path. Nothing was removed; manual review is required.'
    }
    if ($service -and $service.PathName -match '(?i)-D\s+(?:"([^"]+)"|(\S+))') {
        $configuredData = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
        $dataPath = [IO.Path]::GetFullPath($configuredData).TrimEnd('\')
        if (-not $dataPath.StartsWith($target.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'PostgreSQL uses an external data directory. Nothing was removed; manual review is required.'
        }
    }
    if (Test-Path -LiteralPath $target) {
        $links = @(Get-Item -LiteralPath $target; Get-ChildItem -LiteralPath $target -Recurse -Force) |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
        if ($links) { throw 'The PostgreSQL folder contains filesystem links. Nothing was removed; manual review is required.' }
    }
    Write-Host ''
    Write-Host 'PERMANENT RESET: all PostgreSQL 17 databases in this installation will be deleted.' -ForegroundColor Yellow
    Write-Host "Folder: $target"
    Write-Host 'CMH patient records in those databases will be lost. CMH code and app-login settings remain.'
    Write-Host 'Internet access is required. The PostgreSQL installer will ask you to choose a NEW postgres password.'
    if ((Read-Host 'Type DELETE POSTGRES 17 to proceed') -cne 'DELETE POSTGRES 17') {
        throw 'Cancelled. Nothing was removed.'
    }
    $task = Get-ScheduledTask -TaskName 'CMH Smart Serial Server' -ErrorAction SilentlyContinue
    if ($task) {
        Disable-ScheduledTask -InputObject $task | Out-Null
        Stop-ScheduledTask -InputObject $task
    }
    if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
        Stop-Service -Name $serviceName -Force
        (Get-Service -Name $serviceName).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
        & sc.exe delete $serviceName
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove the PostgreSQL service.' }
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Service -Name $serviceName -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
        if (Get-Service -Name $serviceName -ErrorAction SilentlyContinue) {
            throw 'Service is pending deletion. Close Services and pgAdmin, reboot Windows, then run this BAT again.'
        }
    }
    # Only stop PostgreSQL executables from this exact installation.
    Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    # The user deleted the installation folder, so its uninstaller may no longer exist.
    # Remove only PostgreSQL 17's stale registration, not pgAdmin or other products.
    foreach ($base in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
        Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
            $entry = Get-ItemProperty $_.PSPath
            if ($entry.DisplayName -match '^PostgreSQL 17(?:\s|\.|$)') { Remove-Item -LiteralPath $_.PSPath -Recurse -Force }
        }
    }
    foreach ($key in @('HKLM:\SOFTWARE\PostgreSQL\Installations\postgresql-x64-17', 'HKLM:\SOFTWARE\PostgreSQL\Services\postgresql-x64-17')) {
        if (Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force }
    }
    $config = Join-Path $root '.setup\postgres.json'
    if (Test-Path -LiteralPath $config) { Remove-Item -LiteralPath $config -Force }
    Write-Host 'Installing PostgreSQL 17. Use port 5432 and remember the NEW postgres password.' -ForegroundColor Cyan
    & winget install --id PostgreSQL.PostgreSQL.17 --exact --force --interactive --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Installer failed or was cancelled. Run this BAT again when ready.' }
    $installed = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if (-not $installed) { throw 'PostgreSQL 17 service was not created. Complete the installer before running CMH.' }
    Set-Service -Name $serviceName -StartupType Automatic
    Start-Service -Name $serviceName
    (Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    Write-Host 'PostgreSQL is ready. CMH setup will now ask for the NEW postgres password once.' -ForegroundColor Green
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
