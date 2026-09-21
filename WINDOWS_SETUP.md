# CMH Smart Serial — Windows source setup

The Windows source launcher uses **PostgreSQL as the primary database**. It does
not fall back to SQLite when PostgreSQL is unavailable.

## New Windows PC

1. Copy or clone the source into `C:\CMH\CMH_SMS`. For a fresh installation,
   exclude `.env`, `.setup`, `backend\.venv`, `backend\data`,
   `frontend\node_modules`, and development caches from the old PC. This does
   not transfer existing patient records.
2. Install Python 3.12 (enable Add Python to PATH) and Node.js 22 LTS. The launcher
   can attempt Python installation through WinGet if Python is missing.
3. Build the current frontend in Command Prompt:

   ```bat
   cd /d C:\CMH\CMH_SMS\frontend
   npm ci
   npm run build
   ```

   Keep `frontend\dist`: the launcher serves this build and does not build it.
4. Right-click `RUN_WINDOWS.bat` and choose **Run as administrator**. Keep internet
   connected for dependency, PostgreSQL and voice-model downloads.
5. If PostgreSQL is missing, setup opens its installer through WinGet. Use port
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

Open `http://127.0.0.1:8100` and sign in. Keep the Server window open.
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

Existing SQLite files are never deleted or imported automatically. If setup
finds an old SQLite database without a saved PostgreSQL configuration, it stops.
Arrange migration of its records, then explicitly select the PostgreSQL URL.
Creating a new PostgreSQL database does not transfer records from another PC.

## Subsequent runs and automatic startup

Run `RUN_WINDOWS.bat` again. It applies pending migrations and idempotent seed
updates using the saved PostgreSQL connection. Rebuild with `npm run build` after
frontend source changes.

After setup succeeds, run `INSTALL_AUTOSTART_WINDOWS.bat` as administrator under
the same Windows account used for setup. It starts the server at that user's
login, restarts it after crashes, and disables AC sleep/hibernation. Keep the user
signed in for Windows audio; lock with `Win+L` instead of signing out.
`UNINSTALL_AUTOSTART_WINDOWS.bat` removes the scheduled task without deleting data.

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
- **Missing frontend:** run `npm ci` and `npm run build` in `frontend`.
- **Port 8100 occupied:** stop the confirmed existing app before relaunching.

This launcher defaults to development HTTP settings. For approved production
HTTPS/cookie/host settings, see the production section in `README.md`.

The separate frozen EXE installer under `packaging/windows` has its own database
bootstrap and is not the PostgreSQL source deployment documented here.
