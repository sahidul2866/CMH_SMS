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

The launcher installs missing Python and optional eSpeak NG prerequisites with
`winget`, creates the local Python environment, installs changed dependencies,
creates and migrates the database, creates the initial administrator, builds the
uses the bundled prebuilt frontend, configures a private-network firewall rule, starts one LAN-visible
server, waits for readiness, and opens the application.

On the first run, note the administrator password printed in the launcher. A
copy is stored locally at `.setup\INITIAL_ADMIN_LOGIN.txt`. The launcher never
resets an existing administrator or database.

It is safe to run repeatedly. Completed steps are skipped, existing database data is preserved, and only pending database migrations are applied.

## Keep the server running automatically

After `RUN_WINDOWS.bat` completes successfully once, right-click
`INSTALL_AUTOSTART_WINDOWS.bat` and choose **Run as administrator**. It creates
an unlimited Task Scheduler job for the current staff account, disables AC
sleep/hibernation, starts the server at every login, and restarts it after a
crash.

The scheduled job deliberately runs in the signed-in user's interactive
session rather than as a Windows service. This is required for announcements to
play through the Windows sound output. Keep that staff account signed in and
lock the screen with `Win+L` instead of signing out.

To remove automatic startup without deleting data, run
`UNINSTALL_AUTOSTART_WINDOWS.bat`.

## Build the shareable installer EXE

On one internet-connected Windows build PC, run:

```text
BUILD_WINDOWS_INSTALLER.bat
```

The build downloads the offline Bengali model when necessary, freezes FastAPI,
Uvicorn, Python and all dependencies with PyInstaller, and compiles an Inno
Setup installer. The result is:

```text
installer-output\CMH-Smart-Serial-Setup.exe
```

Only that installer EXE needs to be shared with hospital PCs. Target PCs do not
need Python, Node.js, npm, source code or internet. Application data and the
database are stored under `C:\ProgramData\CMH Smart Serial`, outside the
installation folder, so upgrades and uninstall/reinstall cycles do not erase
operational records.

The remaining sections document the same process manually for troubleshooting or controlled installation.

## 1. Install the prerequisites

Open **PowerShell as Administrator** and install Python, Node.js, and Git using `winget`:

```powershell
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Git.Git -e
```

The automatic launcher installs eSpeak NG when possible. For a manual setup,
install it with:

```powershell
winget install --id eSpeak-NG.eSpeak-NG -e
```

Keep the default installation directory (`C:\Program Files\eSpeak NG`) so the
application can find it automatically. This supplies the complete personalized
Bangla and English fallback announcements without internet access.

The recommended higher-quality option is the offline Bengali neural voice. On
the first run, the launcher installs its runtime and downloads Meta's
`facebook/mms-tts-ben` model into `backend\data\models\mms-tts-ben`. After that
download, generation is entirely local. Select **Offline neural** under
**Settings → Queue & display → Announcement**, save, and use **Test selected
voice**. The model is licensed CC BY-NC 4.0 and is included here only for the
hospital's non-commercial internal deployment; see `THIRD_PARTY_MODELS.md`.

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
20260818_0013 (head)
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

## 6. Build and start the application

Build the frontend once:

```powershell
Set-Location C:\CMH\CMH_SMS\frontend
npm run build
```

Start the combined server:

```powershell
Set-Location C:\CMH\CMH_SMS\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8100
```

Wait for:

```text
Application startup complete.
```

Open these addresses in Chrome or Edge:

- Application on server: <http://127.0.0.1:8100>
- Application on wired clients: `http://SERVER-PC-IP:8100`
- API health: <http://127.0.0.1:8100/api/v1/health>
- API documentation: <http://127.0.0.1:8100/docs>

Press `Ctrl+C` to stop the server.

## 7. Free occupied ports

If port `8100` is already in use, open PowerShell as Administrator and identify the listening process:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8100 |
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

Then start the combined server again.

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

In the health response, confirm:

```text
audio.ready: true
audio.bangla_supported: true
```

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

The server must accept TCP port `8100` from the wired CMH subnet. In an
Administrator PowerShell window, replace the example subnet with the address
range approved by CMH ICT:

```powershell
New-NetFirewallRule -DisplayName "CMH Smart Serial LAN" `
  -Direction Inbound -Protocol TCP -LocalPort 8100 `
  -RemoteAddress 192.168.50.0/24 -Action Allow -Profile Domain,Private
```

Do not create an unrestricted Public-profile rule. CMH ICT should assign a
static/DHCP-reserved server address and restrict the switch VLAN and firewall to
the radiographer and reception PCs.

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

### A wired client reports that the API is unavailable

On the server, confirm:

```text
http://127.0.0.1:8100/api/v1/health
```

Then confirm the client can ping the server IP and open
`http://SERVER-PC-IP:8100/api/v1/health`. Never use `localhost` on a client PC.
Check the Cat6 link light, switch/VLAN assignment, Windows firewall scope and
server IP reservation.

### Migration fails

Make sure the command is executed inside the `backend` directory using the project-local Python executable:

```powershell
Set-Location C:\CMH\CMH_SMS\backend
.venv\Scripts\python.exe -m alembic upgrade head
```
