# CMH Smart Serial — Windows Setup Guide

This guide installs the standalone CMH Smart Serial application on a new Windows 10/11 computer and creates a fresh local database. The application does not require the HMS project or its database.

## Automatic installation (recommended)

Place the project on the new PC, open the `CMH_SMS` folder, and double-click:

```text
RUN_WINDOWS.bat
```

If you prefer Git Bash, MSYS2, or Cygwin, run the same launcher through
`run.sh`:

```bash
bash run.sh
```

The launcher installs missing prerequisites with `winget`, creates the local Python environment, installs changed dependencies, creates and migrates the database, loads seed data once, clears occupied application ports, starts both services, waits for readiness, and opens the application.

It is safe to run repeatedly. Completed steps are skipped, existing database data is preserved, and only pending database migrations are applied.

The remaining sections document the same process manually for troubleshooting or controlled installation.

## 1. Install the prerequisites

Open **PowerShell as Administrator** and install Python, Node.js, and Git using `winget`:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Git.Git -e
```

Close PowerShell, open it again, and confirm the installations:

```powershell
py -3.12 --version
node --version
npm --version
git --version
```

Expected minimum versions:

- Python 3.11+
- Node.js 20+
- npm 10+

## 2. Copy or clone the project

Place the project in a simple path without unusual characters, for example:

```text
C:\CMH\CMH_SMS
```

If using Git:

```powershell
New-Item -ItemType Directory -Force C:\CMH
Set-Location C:\CMH
git clone <repository-url> CMH_SMS
Set-Location C:\CMH\CMH_SMS
```

If the folder was copied using a USB drive or shared folder:

```powershell
Set-Location C:\CMH\CMH_SMS
```

Do not copy these generated folders from another computer:

```text
backend\.venv
frontend\node_modules
frontend\dist
frontend\.angular
```

## 3. Create the backend environment

Run from the `CMH_SMS` project directory:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

The environment belongs only to this standalone project.

## 4. Create and migrate a new database

The default Windows installation uses an independent SQLite database at:

```text
backend\data\cmh_sms.db
```

Create the database and all tables by running the Alembic migrations:

```powershell
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
```

Load the initial CMH configuration and demonstration data:

```powershell
.venv\Scripts\python.exe -m app.seed
```

Confirm the installed migration:

```powershell
.venv\Scripts\python.exe -m alembic current
```

Expected result:

```text
20260722_0003 (head)
```

The seed command is idempotent. Running it again updates system configuration and demo data without duplicating the daily demonstration queue.

Return to the project directory:

```powershell
Set-Location ..
```

## 5. Install the frontend

```powershell
Set-Location frontend
npm ci
Set-Location ..
```

## 6. Start the application

Use two PowerShell windows.

### PowerShell window 1 — backend

```powershell
Set-Location C:\CMH\CMH_SMS\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

Wait for:

```text
Application startup complete.
```

### PowerShell window 2 — frontend

```powershell
Set-Location C:\CMH\CMH_SMS\frontend
npm start -- --host 127.0.0.1 --port 4300
```

Open these addresses in Chrome or Edge:

- Application: <http://127.0.0.1:4300>
- API health: <http://127.0.0.1:8100/api/v1/health>
- API documentation: <http://127.0.0.1:8100/docs>

Press `Ctrl+C` in each PowerShell window to stop the services.

## 7. Free occupied ports

If port `8100` or `4300` is already in use, open PowerShell as Administrator and identify the listening process:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8100,4300 |
    Select-Object LocalPort, OwningProcess
```

Inspect a process before stopping it:

```powershell
Get-Process -Id <PID>
```

Stop only the confirmed process:

```powershell
Stop-Process -Id <PID> -Force
```

Then start the backend and frontend again.

## 8. Verify the new database

With the backend running, verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8100/api/v1/health
Invoke-RestMethod http://127.0.0.1:8100/api/v1/doctors
Invoke-RestMethod http://127.0.0.1:8100/api/v1/waiting-rooms
```

The seed should provide:

- Four shared waiting rooms
- Four doctors
- Queue, display, and announcement settings
- Realistic demonstration tokens

## 9. Run automated checks

Backend tests:

```powershell
Set-Location C:\CMH\CMH_SMS\backend
.venv\Scripts\python.exe -m pytest -q
```

Frontend production build:

```powershell
Set-Location C:\CMH\CMH_SMS\frontend
npm run build
```

## 10. Database backup and reset

### Back up the database

Stop the backend and copy:

```text
backend\data\cmh_sms.db
```

Example:

```powershell
Copy-Item backend\data\cmh_sms.db "D:\CMH-Backups\cmh_sms-$(Get-Date -Format yyyyMMdd-HHmm).db"
```

### Create a completely fresh database

This deletes local application data. First stop the backend and make a backup. Then:

```powershell
Remove-Item backend\data\cmh_sms.db
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app.seed
```

## 11. Windows Firewall

No inbound firewall rule is normally required for a single-computer demonstration using `127.0.0.1`.

Do not expose ports to the hospital LAN until the application has production authentication, RBAC, HTTPS/WSS, approved firewall rules, and a configured server address. The current local setup is intended for development and demonstration.

## Troubleshooting

### `py -3.12` is not recognized

Restart PowerShell after installing Python. If it still fails, reinstall Python and enable **Add Python to PATH**.

### PowerShell cannot find the virtual environment

Confirm that the current directory is `C:\CMH\CMH_SMS` before creating it and that this file exists:

```text
backend\.venv\Scripts\python.exe
```

### `npm` is not recognized

Restart PowerShell after installing Node.js. Confirm with `node --version` and `npm --version`.

### Frontend reports that the API is unavailable

Confirm the backend is running on port `8100` and open:

```text
http://127.0.0.1:8100/api/v1/health
```

The backend accepts the Angular development UI on ports `4200` and `4300`,
using either `localhost` or `127.0.0.1`. Restart the backend after changing or
updating the application so the CORS configuration is reloaded.

### Migration fails

Make sure the command is executed inside the `backend` directory using the project-local Python executable:

```powershell
Set-Location C:\CMH\CMH_SMS\backend
.venv\Scripts\python.exe -m alembic upgrade head
```
