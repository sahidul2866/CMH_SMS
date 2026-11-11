param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 8100
)
$ErrorActionPreference = 'Stop'
try {
    $project = [IO.Path]::GetFullPath($ProjectDir).TrimEnd('\')
    $python = Join-Path $project 'backend\.venv\Scripts\python.exe'
    $launchers = @('START_CMH_FOREVER_WINDOWS.bat', 'START_BACKEND_WINDOWS.bat')
    $processes = @(Get-CimInstance Win32_Process)
    function Is-ProjectServer($process) {
        $command = [string]$process.CommandLine
        foreach ($launcher in $launchers) {
            if ($command.IndexOf((Join-Path $project $launcher), [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        }
        return ([string]$process.ExecutablePath -ieq $python) -and
            ($command -match '\buvicorn\b') -and ($command -match 'app\.main:app')
    }
    $roots = @($processes | Where-Object { Is-ProjectServer $_ })
    $owned = [Collections.Generic.HashSet[int]]::new()
    foreach ($process in $roots) { [void]$owned.Add([int]$process.ProcessId) }
    # Include helper/launcher children so the restart loop cannot respawn Python.
    do {
        $added = $false
        foreach ($process in $processes) {
            if ($owned.Contains([int]$process.ParentProcessId) -and $owned.Add([int]$process.ProcessId)) { $added = $true }
        }
    } while ($added)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        if (-not $owned.Contains([int]$listener.OwningProcess)) {
            throw "Port $Port belongs to another application or project. No processes were stopped."
        }
    }
    $task = Get-ScheduledTask -TaskName 'CMH Smart Serial Server' -ErrorAction SilentlyContinue
    if ($task) {
        $arguments = ($task.Actions | ForEach-Object { $_.Arguments }) -join ' '
        $expected = Join-Path $project 'START_CMH_FOREVER_WINDOWS.bat'
        if ($arguments.IndexOf($expected, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw 'The CMH scheduled task belongs to another project folder. No processes were stopped.'
        }
        # Suppress the one-minute watchdog throughout migrations and the build.
        Disable-ScheduledTask -TaskName 'CMH Smart Serial Server' | Out-Null
        Stop-ScheduledTask -TaskName 'CMH Smart Serial Server'
    }
    # Stop restart-loop roots first, then remaining captured children.
    $ordered = @($roots | ForEach-Object { [int]$_.ProcessId }) + @($owned)
    foreach ($processId in ($ordered | Select-Object -Unique)) {
        if ($processId -eq $PID) { throw 'Refusing to stop the current updater process.' }
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            try { Stop-Process -Id $processId -Force -ErrorAction Stop }
            catch {
                # The scheduled task may have terminated this child in parallel.
                if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { throw }
            }
        }
    }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
            Write-Host 'Previous CMH server stopped. Automatic recovery will be enabled again after setup.'
            exit 0
        }
        Start-Sleep -Milliseconds 500
    }
    throw "The CMH server did not release port $Port."
} catch {
    Write-Error "Could not stop the existing CMH server: $_"
    exit 1
}
