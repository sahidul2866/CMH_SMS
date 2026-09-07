# CMH Smart Serial

Standalone serial and appointment management product. It borrows the parent HMS's Angular/FastAPI conventions, but has an independent domain, API, UI, and deployment boundary.

## Current vertical slice

- Reception creates a patient token and it joins the doctor's queue immediately.
- Reception registers patients, schedules appointments, and checks arrivals into the live queue.
- Doctor sees a live queue, calls next, or calls a selected patient.
- The waiting-room screen shows the current call and next patients.
- The backend host queues and plays patient announcements directly through its connected sound output; client browsers remain silent.
- Room-scoped WebSockets push doctor calls to the correct TV immediately; five-second polling remains as automatic recovery.
- Alembic owns the standalone database schema.
- Seed data provides four waiting rooms, four doctors, and realistic live queues.
- The default database is `backend/data/cmh_sms.db`; `CMH_SMS_DATABASE_URL` can point to PostgreSQL.

## Run

macOS/Linux:

```bash
./run.sh
```

On the first run, the launcher:

1. Creates a permission-restricted `.env` with random PostgreSQL and initial
   administrator passwords.
2. Installs and starts the operating system’s native PostgreSQL service
   (APT on Debian/Ubuntu or Homebrew on macOS).
3. Creates the physical `cmh_sms` database and restricted application role.
4. Installs backend/frontend dependencies, applies every Alembic migration and
   creates the initial administrator.
5. Builds Angular and starts one LAN-visible FastAPI process on port `8100`.

The initial administrator password is printed once. Subsequent runs preserve the
database, users and operational records and apply only pending migrations.

Windows (Git Bash, MSYS2, or Cygwin):

```bash
bash run.sh
```

Windows users can alternatively double-click `RUN_WINDOWS.bat`. On Windows,
`run.sh` automatically delegates to that native launcher. `RUN_WINDOWS.bat` is
the recommended one-command installer: it can install Python and optional
eSpeak NG through WinGet, uses the bundled prebuilt frontend, creates the initial administrator and local database,
configures private-LAN firewall access, builds the UI, and starts the server.
The initial login is printed once and saved in
`.setup\INITIAL_ADMIN_LOGIN.txt` on that Windows PC.

The launcher creates the project-local Python environment, installs dependencies, runs every migration, loads idempotent seed data, builds the UI and starts the combined server.
It builds the frontend and serves the frontend, API and WebSocket from one LAN-visible process. If port `8100` is already occupied, it stops the listening process before launching the project.

- Application: `http://SERVER-PC-IP:8100`
- API: `http://SERVER-PC-IP:8100/api/v1`
- API docs in development: `http://127.0.0.1:8100/docs` (disabled in production)

## Wired LAN deployment

Connect the server, four radiographer PCs and reception PC to the same Gigabit
switch using dedicated Cat6 cables. Give the server a static address or DHCP
reservation, for example `192.168.50.10`. On every client, open:

```text
http://192.168.50.10:8100
```

No frontend installation is required on client PCs. Do not use `localhost`
there—`localhost` always means the client PC itself. Allow inbound TCP port
`8100` on the server firewall for the approved CMH LAN/VLAN only. Internet and
ngrok are not required for normal operation.

## Roles and access

- `admin`: all modules, settings, reports and user-account creation.
- `reception`: patient registration, queue viewing and priority management.
- `radiographer`: assigned doctor queue, call/recall and service transitions.
- `auditor`: read-only reports and audit trail.
- `display`: waiting-room display and realtime updates only.

Authentication uses random server-side sessions stored in PostgreSQL and an
HttpOnly, SameSite=Strict cookie. Radiographer accounts are bound to one doctor;
the API enforces this even if a client request is modified.

Administrators create staff accounts from **Settings → User accounts and
roles**. Use a separate display account for each waiting-room display device.

Form dropdowns are database-backed master data. Administrators can add, rename,
order, enable or disable departments, patient titles, sex values, service
categories, rank/relationship values, priority categories and appointment
reasons from **Settings → Configurable dropdown values**. Disabled entries are
hidden from new records while historical records retain their stored value.

The **Appointments** workspace searches or registers patients, books available
schedule slots, confirms or cancels bookings, and checks arrivals into the
queue. The server enforces capacity and holiday rules; repeated check-in returns
the existing token instead of generating a duplicate.

Appointment and token SMS messages use a persistent outbox. Configure
`CMH_SMS_SMS_GATEWAY_URL` and, when required, `CMH_SMS_SMS_GATEWAY_TOKEN` for the
CMH-approved HTTP SMS gateway. Without a configured gateway, messages remain
visible as queued in **Settings → SMS notification outbox** and no external
network request is attempted.

## PostgreSQL operations

The database is managed by the server’s native PostgreSQL service and stored in
the operating system’s standard PostgreSQL data directory. It starts
automatically when the server boots.

```bash
pg_isready -h 127.0.0.1 -p 5432
PGPASSWORD="$CMH_SMS_POSTGRES_PASSWORD" pg_dump \
  -h 127.0.0.1 -U cmh_sms -d cmh_sms > cmh_sms_backup.sql
```

Stopping the application with `Ctrl+C` leaves the native PostgreSQL service
running. No Docker installation or container runtime is used.

## Server-PC audio

The same PC hosts the frontend, backend, database, WebSocket service and audio
playback. Connect its USB sound card or 3.5 mm line output to a PA amplifier.
Calls and recalls from every doctor enter one lossless FIFO announcement queue.
The Bangla portion uses prerecorded neural-voice prompts around the dynamically
spoken patient name and token number; the original full English announcement
follows. The server finishes each announcement before playing the next one, so
simultaneous doctor calls never overlap.
On Ubuntu/Debian install the audio tools once:

```bash
sudo apt install espeak-ng alsa-utils
```

macOS uses its built-in `say` and `afplay` commands automatically.

Windows servers use eSpeak NG for dynamic English generation and the
built-in Windows WAV player. Install the current eSpeak NG Windows package from
the official project release before starting the application. The executable is
detected from `PATH` or `C:\Program Files\eSpeak NG\espeak-ng.exe`.

Check `http://127.0.0.1:8100/api/v1/health`. Audio is correctly configured when
`audio.ready` and `audio.bangla_supported` are both `true`.

Useful environment variables:

- `CMH_SMS_AUDIO_ENABLED=false` disables physical playback.
- `CMH_SMS_AUDIO_CACHE=/var/lib/cmh-smart-serial/audio` changes the generated WAV cache.
- `CMH_SMS_AUDIO_PLAY_COMMAND='aplay -D plughw:CARD=Device $file'` selects a specific ALSA output.
- `CMH_SMS_NGROK=true ./run.sh` enables the optional public tunnel; LAN deployment does not require ngrok.

## Database commands

Run from `backend/` after the environment has been created:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
```

Set `CMH_SMS_DATABASE_URL` before `./run.sh` to use an external PostgreSQL database. No HMS database or runtime is used.

For a fresh Windows PC, follow [WINDOWS_SETUP.md](WINDOWS_SETUP.md).

## Production go-live

Production mode fails closed unless PostgreSQL, HTTPS cookies and an approved
host allow-list are configured. Set these values in the root `.env`:

```text
CMH_SMS_ENVIRONMENT=production
CMH_SMS_ALLOWED_HOSTS=queue.cmh.local,192.168.50.10
CMH_SMS_PUBLIC_HTTPS=true
CMH_SMS_COOKIE_SECURE=true
CMH_SMS_TLS_CERTFILE=/etc/cmh-sms/tls/fullchain.pem
CMH_SMS_TLS_KEYFILE=/etc/cmh-sms/tls/private.key
```

Use a CMH-approved certificate trusted by every managed client. Keep
`CMH_SMS_CORS_ORIGINS` empty for same-origin deployment. Production startup
rejects SQLite, wildcard hosts, insecure cookies and non-HTTPS public mode.
`GET /api/v1/ready` verifies database readiness; `/api/v1/health` reports the
audio subsystem.

Install `deploy/cmh-sms-backup.service` and
`deploy/cmh-sms-backup.timer` under `/etc/systemd/system`, adjust the service
account/project path if necessary, then enable the daily backup:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cmh-sms-backup.timer
sudo systemctl list-timers cmh-sms-backup.timer
```

Backups are PostgreSQL custom-format files with permissions restricted to the
service account. The default retention is 30 days and can be changed with
`CMH_SMS_BACKUP_RETENTION_DAYS`. A CMH-approved off-host encrypted copy and a
documented restore drill are still required for the approved RPO/RTO.

### MRI reception and shared waiting workflow

- Reception saves the MRI registration without assigning a radiographer or consultation room. The annual serial starts at `00001/YY`. Existing registrations keep their identifiers.
- Select a radiographer to open the shared waiting list. Any radiographer can call a waiting patient from any waiting area. Calling records the responsible radiographer and their configured room; another radiographer cannot call or start that patient while they are being handled.
- VIPs appear first and use **Call physically**, which starts service without a PA announcement. Cancel actions require a reason.
- **Settings → Dropdown options** manages patient sources (OPD, IPD/ward, referral and custom options), military designations, priorities and room choices. Designations can be marked as VIP. Honorifics such as Mr./Mrs. are not part of reception registration.
- **Settings → Rooms & devices** configures radiographer rooms and consoles; **Console settings** configures queue, display and audio behavior. Saved settings and dropdown edits survive startup seeding.
- Dashboard number buttons open patient details. **Reception Report → Today’s report** exports today's MRI register to Excel; PDF and date-range filters are also available. Modal forms support Tab, Shift+Tab, Enter and Escape.
