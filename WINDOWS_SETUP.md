# CMH Smart Serial — Windows source setup

The Windows source launcher uses **PostgreSQL as the primary database**. It does
not fall back to SQLite when PostgreSQL is unavailable.

## New Windows PC

1. Copy or clone the source into `C:\CMH\CMH_SMS`. For a fresh installation,
   exclude `.env`, `.setup`, `backend\.venv`, `backend\data`,
   `frontend\node_modules`, and development caches from the old PC. This does
   not transfer existing patient records.
2. Install Python 3.12 (enable Add Python to PATH) and Node.js 22 LTS. The launcher
   can attempt Python and Node.js installation through WinGet if missing.
3. Right-click `RUN_WINDOWS.bat` and choose **Run as administrator**. Keep internet
   connected for dependency, PostgreSQL and voice-model downloads. Like `run.sh`,
   the launcher installs frontend dependencies with `npm ci` when `node_modules`
   is missing and builds the current source with `npm run build` on every launch.
   No manual frontend build or bundled `frontend\dist` is required. Build failures
   stop setup before the server starts.
4. If PostgreSQL is missing, setup opens its installer through WinGet. Use port
   **5432**, install the database server, and remember the `postgres` administrator
   password. Enter that password at the launcher's hidden password prompt. For an
   existing local installation, enter its existing administrator password.

The launcher configures the PostgreSQL Windows service for automatic startup,
creates a restricted login named `cmh_sms` with a generated password, creates the
`cmh_sms` database owned by that login, applies all Alembic migrations, and seeds
missing initial configuration/accounts. Existing roles, passwords and records
are preserved. The PostgreSQL administrator password is not saved.

The application connection is saved in `.setup\postgres.json`, restricted to the
setup account, SYSTEM and local administrators. Initial application credentials
are saved in `.setup\INITIAL_ADMIN_LOGIN.txt`. Keep `.setup` private and retain it
on this PC for subsequent launches. The root `.env` is not loaded by the Windows
source launcher.

Open `http://127.0.0.1:8100` and sign in. Setup also installs and starts the
`CMH Smart Serial Server` scheduled task for the current Windows account.
Check `http://127.0.0.1:8100/api/v1/ready` for database readiness.

## Existing or remote PostgreSQL database

To use an existing database instead of provisioning the default local instance,
set its URL in the Command Prompt used to launch setup:

```bat
cd /d C:\CMH\CMH_SMS
set "CMH_SMS_DATABASE_URL=postgresql+psycopg://APP_USER:URL_ENCODED_PASSWORD@DB_HOST:5432/DB_NAME"
RUN_WINDOWS.bat
```

The database and login must already exist and the login must have permission to
run migrations. URL-encode special characters in credentials. Setup verifies and
saves the connection, skips local PostgreSQL installation/provisioning, and uses
it for migrations, seeding, normal startup and automatic startup. Prefer using
`.setup\postgres.json` for subsequent launches; an explicit environment URL takes
precedence. SQLite URLs are rejected.

Existing SQLite files are preserved and do not block PostgreSQL setup. The
launcher prints a notice when it finds `backend\data\cmh_sms.db`; this is not
a PostgreSQL error. SQLite records are not imported automatically. Restore a
PostgreSQL backup or arrange migration if those records are needed. The Windows
launchers disable the optional SQLite snapshot so copied snapshot settings cannot
overwrite a legacy SQLite database.
Creating a new PostgreSQL database does not transfer records from another PC.

## Subsequent runs and automatic startup

Run `RUN_WINDOWS.bat` again. It applies pending migrations and idempotent seed
updates using the saved PostgreSQL connection and rebuilds the current frontend
source automatically. Before relaunching for an update, run
`STOP_CMH_WINDOWS.bat` as administrator and wait for port 8100 to be released.

`RUN_WINDOWS.bat` enables automatic recovery after a successful build:

- If the application process exits, the supervisor retries after 10 seconds,
  including when PostgreSQL is temporarily unavailable during startup.
- If the supervisor/server window closes, Task Scheduler attempts to start it
  again at the next one-minute check. Checks do not start another instance while
  the scheduled task is running.
- After a reboot, the server starts when the setup user signs in. Keep this user
  signed in for Windows audio; lock with `Win+L` instead of signing out.
- Recovery launches the built app using the saved configuration. It does not
  reinstall dependencies, rebuild the frontend, or rerun migrations.

Run `STOP_CMH_WINDOWS.bat` as administrator for an intentional maintenance stop.
It disables the scheduled task before stopping it, so automatic recovery stays
off until you run `RUN_WINDOWS.bat` or `INSTALL_AUTOSTART_WINDOWS.bat` again.
Closing a server window is no longer a permanent stop.

`INSTALL_AUTOSTART_WINDOWS.bat` can also enable recovery without rebuilding under
the same Windows account used for setup; it additionally disables AC sleep and
hibernation. `UNINSTALL_AUTOSTART_WINDOWS.bat` removes the scheduled task without
deleting data. Run these management scripts as administrator.

Recovery requires Windows to be awake and the setup account signed in. It handles
process exits, not a process that remains running but hangs. Persistent configuration
errors still need correction; retries cannot repair a failed disk or database.

### Verify recovery on the Windows server

Automated launcher tests can be run from the project root on Windows:

```bat
backend\.venv\Scripts\python.exe -m unittest discover -s scripts/tests -p "test_windows*.py" -v
```

The **Windows launcher tests** GitHub Actions workflow runs this suite on a
Windows runner after relevant pushes and pull requests. Once the workflow is on
the default branch, it can also be started from GitHub's Actions tab using
**Run workflow**, including from a Mac. No Windows installation is needed locally.

The suite checks PostgreSQL launch failures and recovery, executes the actual
batch retry loop with a disposable app, and executes the PowerShell task setup
and maintenance commands with mocked scheduling operations. It never changes
the real CMH scheduled task. On macOS, the Windows-native tests are explicitly
skipped. These automated tests do not prove real Task Scheduler relaunch, login
startup, database integration, or speaker output; verify those on Windows below.

1. Run `RUN_WINDOWS.bat` as administrator and check `/api/v1/ready` returns 200.
2. In Task Manager, end the app's Uvicorn Python process. Confirm readiness returns
   after the 10-second retry plus startup time.
3. Close the Always On Server window. Confirm it reopens and readiness returns
   after the next one-minute check plus startup time.
4. Run `STOP_CMH_WINDOWS.bat`. Confirm port 8100 is released and the server stays
   stopped for more than one minute. Enable it again using the install script.
5. Restart Windows and sign in as the setup user. Confirm readiness and test an
   announcement. Inspect the task in Task Scheduler if recovery does not occur.

PostgreSQL runs as a separate Windows service. Closing the application does not
stop the database service.

## LAN and announcements

On other PCs on the same private LAN, open `http://SERVER-PC-IP:8100`, using the
address printed by the launcher. Only the server needs this codebase. The launcher
adds a private-network inbound TCP 8100 firewall rule when run as administrator.
Use a static address or DHCP reservation for the server.

Connect speakers/the PA to the server. Setup attempts eSpeak NG installation and
downloads the offline Bengali voice model. Check `/api/v1/health` for
`audio.ready` and `audio.bangla_supported`.

## PostgreSQL backup

Use PostgreSQL's `pg_dump`, not a copy of `backend\data\cmh_sms.db`. For the default
local setup, use the application password stored in `.setup\postgres.json`:

```bat
"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h 127.0.0.1 -p 5432 -U cmh_sms -W -F c -f "D:\CMH-Backups\cmh_sms.dump" cmh_sms
```

Create the backup directory first; adjust the executable path for your installed
PostgreSQL version. Keep backups outside the project and verify restores.

## Troubleshooting

- **No WinGet:** install PostgreSQL manually from the official Windows installer,
  then rerun setup as administrator.
- **Connection failure:** check PostgreSQL in Windows Services, port 5432, the
  saved connection, and credentials. Setup stops instead of using SQLite.
- **Existing `cmh_sms` role with a different password:** provide its correct
  application connection through `CMH_SMS_DATABASE_URL`; setup does not reset it.
- **Multiple PostgreSQL services/non-default port:** supply the intended existing
  database URL explicitly.
- **Frontend build failure:** fix the reported npm/build error and rerun the launcher.
  If dependencies changed, run `npm ci` in `frontend` first.
- **Port 8100 occupied:** stop the confirmed existing app before relaunching.

This launcher defaults to development HTTP settings. For approved production
HTTPS/cookie/host settings, see the production section in `README.md`.

The separate frozen EXE installer under `packaging/windows` has its own database
bootstrap and is not the PostgreSQL source deployment documented here.
