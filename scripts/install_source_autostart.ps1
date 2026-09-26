$ErrorActionPreference = 'Stop'
try {
    $project = Split-Path -Parent $PSScriptRoot
    foreach ($relative in @('.setup\windows.env.bat', 'backend\.venv\Scripts\python.exe', 'START_CMH_FOREVER_WINDOWS.bat')) {
        if (-not (Test-Path -LiteralPath (Join-Path $project $relative))) {
            throw 'Run RUN_WINDOWS.bat to finish setup first.'
        }
    }
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $server = Join-Path $project 'START_CMH_FOREVER_WINDOWS.bat'
    $action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument ('/d /c ""{0}""' -f $server) -WorkingDirectory $project
    $login = New-ScheduledTaskTrigger -AtLogOn -User $user
    # No duration: keep checking indefinitely, including after a clean window close.
    $watchdog = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName 'CMH Smart Serial Server' -Action $action -Trigger @($login, $watchdog) `
        -Principal $principal -Settings $settings -Force | Out-Null
    Enable-ScheduledTask -TaskName 'CMH Smart Serial Server' | Out-Null
    Start-ScheduledTask -TaskName 'CMH Smart Serial Server'
} catch {
    Write-Error "Could not install/start CMH automatic recovery: $_"
    exit 1
}
