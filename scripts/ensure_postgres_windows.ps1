$ErrorActionPreference = 'Stop'
try {
    $services = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue)
    if ($services.Count -eq 0) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Install PostgreSQL from https://www.postgresql.org/download/windows/ and rerun setup.'
        }
        Write-Host 'Install PostgreSQL on port 5432. Remember the postgres administrator password.'
        & winget install --id PostgreSQL.PostgreSQL.17 --exact --interactive --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL installer failed or was cancelled.' }
        $services = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue)
    }
    if ($services.Count -ne 1) {
        throw 'Expected one local PostgreSQL service. For multiple instances, set CMH_SMS_DATABASE_URL to the intended database.'
    }
    Set-Service -Name $services[0].Name -StartupType Automatic
    Start-Service -Name $services[0].Name
    (Get-Service -Name $services[0].Name).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
} catch {
    Write-Host "ERROR: $($_.Exception.Message) Run RUN_WINDOWS.bat as administrator."
    exit 1
}
