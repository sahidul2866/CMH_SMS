# CMH Smart Serial

Standalone serial and appointment management product. It borrows the parent HMS's Angular/FastAPI conventions, but has an independent domain, API, UI, and deployment boundary.

## Current vertical slice

- Reception creates a patient token and it joins the doctor's queue immediately.
- Reception registers patients, schedules appointments, and checks arrivals into the live queue.
- Doctor sees a live queue, calls next, or calls a selected patient.
- The waiting-room screen shows the current call and next patients.
- The backend host queues and plays patient announcements directly through its connected sound output; client browsers remain silent.
- Authenticated WebSocket change notifications keep reception, radiographer queues, dashboards and displays current. Connected idle screens make no periodic data requests; a 30-second fallback runs only while disconnected or recovering from a failed fetch.
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
the recommended one-command installer: it can install Python, Node.js and optional
eSpeak NG through WinGet, builds the current frontend source, provisions the local PostgreSQL service, application role and database, creates the initial administrator,
configures private-LAN firewall access and starts the server. Frontend dependencies are installed with `npm ci` when
`node_modules` is missing, and `npm run build` runs on every launch, just as in
`run.sh`. A failed build stops setup. PostgreSQL installation prompts for its administrator password;
the application connection is saved in `.setup\postgres.json`.
The initial login is printed once and saved in
`.setup\INITIAL_ADMIN_LOGIN.txt` on that Windows PC.

The launchers create the project-local Python environment, install dependencies, run every migration, load idempotent seed data and start the combined server.
The frontend, API and WebSocket are served from one LAN-visible process. Both source launchers rebuild the frontend on every launch. On Windows, if port `8100` is already occupied, the launcher stops with an error so you can identify and stop the existing service.

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

- Reception can select an optional room/radiographer during MRI registration, or use **Assign room / radiographer** on an unassigned waiting patient. Leaving it blank keeps the patient available to any radiographer. The annual serial starts at `00001/YY`. Existing registrations keep their identifiers.
- Select a radiographer to open the shared waiting list. Radiographers can assign an unassigned patient to any active radiographer/room. Once assigned, only the assigned radiographer or a radiographer in that room can call or reassign the patient. **Call next patient** skips assignments belonging to other rooms. Reassignment is available for waiting or skipped patients and requires a reason; reception cannot override an existing assignment. VIP patients follow the same assignment rules and are called physically. Calling records the responsible radiographer and room.
- VIPs appear first and use **Call physically**, which starts service without a PA announcement. Cancel actions require a reason.
- **Settings → Dropdown options** manages patient sources (OPD, IPD/ward, referral and custom options), military designations, priorities and room choices. Designations can be marked as VIP. Honorifics such as Mr./Mrs. are not part of reception registration.
- **Settings → Console settings** configures radiographer rooms, devices, queue, display and audio behavior. Saved settings and dropdown edits survive startup seeding.
- Dashboard number buttons open patient details. **Reception Report → Today’s report** exports today's MRI register to Excel; PDF and date-range filters are also available. Modal forms support Tab, Shift+Tab, Enter and Escape.

### Reception and radiographer improvements

- **Settings → Radiographers** lets directory administrators add radiographers, edit names and corresponding room numbers together, and remove them from the active directory. Removal preserves historical records and requires staff accounts, active patients and pending appointments to be resolved first.
- **Radiographers → Radiographer availability** shows every active radiographer’s room and occupied/available state, updating when patient activity changes. Called, recalled and in-service patients count as occupied. Queue actions remain restricted to the signed-in radiographer’s assignment.
- **Reception → Waiting patients → Edit** updates registration details while preserving the serial, date and queue assignment. The server rejects an edit if the patient has already been called.
- **Reception Report → MRI summary** accepts inclusive from/to dates, including ranges across months (up to 367 days). Drill-downs and Excel/PDF exports use the loaded report’s range and counting basis. Existing API clients can continue using `month=YYYY-MM`.
- **Settings → Console settings → Patient input fields** controls enabled/disabled and required/optional registration fields. Name remains enabled and required. Disabled inputs are hidden and rejected by the API; edits preserve their historical values. Classification requirements apply only when relevant to the patient type. Custom text, number, date and dropdown fields can be added in the same panel. Definitions are stored in application settings and values in `queue_tokens.custom_fields` (PostgreSQL JSONB), introduced by migration `20260921_0021`; adding further custom fields requires no schema migration. Saved custom field types/keys cannot change and fields are retired by disabling them. Custom values appear in patient details and reception Excel exports, including historical values of disabled fields.
- Role integration tests use isolated test accounts for admin, radiographer, a custom `head_of_dept` role, reception, auditor and display; they do not change deployed user accounts.

### MRI summary mapping

Settings → MRI summary mapping lets users with `settings.manage` choose a report column (or Needs review) for up to 24 report-group combinations plus individual overrides for every active rank/designation (Self/Family × Serving/Retired). Custom ranks appear automatically; select Use report-group mapping to inherit the group rule. Military combinations use patient type, service status and rank group; family combinations use the sponsor’s rank and status. Civil entitled, RE and CNE have their own mappings. Rank groups remain configurable under Dropdown options → Designation / Rank. Restore default mappings resets the draft; Save mappings persists it.

Mappings start with the existing report rules and survive restarts. Changes are audited and apply when creating registrations or saving classification edits, including waiting-patient edits. Calculated categories are refreshed when classification details are edited. Directly chosen categories remain fixed until explicitly replaced in Report classification. Incomplete inputs remain Needs review; required family relationship and sponsor-rank validation still applies. Report columns and export layouts remain fixed.

### User accounts and temporary passwords

Administrators can create roles and users, assign roles, and reset passwords for all accounts, including other administrators. New accounts and administrator-reset passwords require a password change immediately after login. Until then, operational API and websocket access is blocked. Resetting a password revokes existing sessions; changing it clears the requirement.

Run the usual migration and seed steps (`cd backend`, `.venv/bin/alembic upgrade head`, `.venv/bin/python -m app.seed`) with deployment environment variables loaded. The seed creates missing built-in roles and these accounts: the configured administrator, `reception`, `radiographer`, `radiographer2`, `radiographer3`, `radiographer4`, `radiography_head`, `auditor`, and `display`. Radiographers are assigned to the four seeded directory entries. The administrator uses `CMH_SMS_ADMIN_PASSWORD`; staff use `CMH_SMS_SEED_USER_PASSWORD`, falling back to that administrator bootstrap password. Supply one of these environment variables to create staff accounts; no hardcoded password is used. Existing accounts, passwords and assignments are preserved on subsequent seed runs.

`mri_rank_mapping_initialized` is an internal one-time seed marker, excluded from the settings UI. It prevents initial rank mappings from overwriting administrator edits.

The MRI mapping editor refreshes automatically while open. Active patient-type, entitlement and service-status report codes determine which combinations appear; current dropdown labels are shown, including aliases sharing a report code. Adding or renaming a rank updates its rows, and disabling/removing it hides them. Unsaved edits on remaining rows survive refresh. Saved rules for disabled values are retained for re-enabling, while existing patient classifications remain unchanged. A save made against an outdated dropdown list requests review of the refreshed rows before saving again.

### Illustrated user manual

Select **User manual** beside **Sign out** to open the offline guide in a new tab. It covers administrator settings, users, roles, temporary passwords, required fields, dropdowns, MRI mappings, radiographer rooms, console settings and daily workflows. Screenshots use an isolated training database. The guide includes a table of contents, full-size screenshot links and **Print / Save PDF**. Source and screenshots live in `frontend/public/manual/` and are copied into the frontend build.

### Dashboard and searchable ranks

The dashboard overview fits one viewport and contains a Completed vs Waiting pie chart and a patient-status bar chart. The All / VIP / Non-VIP filter applies to aggregates, room metrics and patient drilldowns while preserving role scope. Pie percentages include only waiting and completed records; called, in-service and other statuses remain visible in the status chart. Patient-detail pages remain separate from the compact overview.

Designation / Rank, Sponsor rank and the classification editor’s Patient rank use a single searchable combobox. Type to filter, click or use Up/Down and Enter to select, Escape to dismiss, and Tab to leave. Only selected option values are saved. The illustrated manual documents both workflows.

### Direct MRI classification and field loading

Report classification now offers **Choose report category** (no classification inputs required) and **Calculate from patient details**. Direct choices are validated against the fixed MRI report columns, audited, and retained through ordinary patient edits and mapping changes. Recalculating from inputs explicitly returns the record to automatic classification. Migration `20260921_0022` adds the classification source without changing existing categories.

The dialog loads its own choices using the patient-registration permission, shows loading/retry states and explains disabled inputs. MRI mapping settings distinguish group defaults from rank overrides and include examples. The offline manual covers both classification routes and configurable/custom patient fields.

### Bengali pronunciation and announcement languages

Reception can edit **Name in Bengali for announcements** when adding or editing a
waiting patient. Leaving the original name field suggests a Bengali spelling;
**Suggest Bengali spelling** can replace it. Suggestions run locally using common
name spellings and phonetic rules. Review names and abbreviations before saving.
The Bengali spelling is saved separately; the original name and English speech
are preserved. Older registrations without a Bengali spelling receive an offline
suggestion when called. The complete Bengali sentence uses one voice, including
when no service number is present. Unsupported name scripts fall back to the
spoken token identifier if no Bengali spelling has been provided.

In **Settings → Console settings → Announcement → Announcements**, choose **Off**,
**Bangla only**, **English only**, or **Both — Bangla then English**, then save.
Off clears pending audio and suppresses future announcements; a clip already
playing may finish. Patient calls and visual display updates continue. The server
must also have audio enabled for playback. Existing saved language preferences
remain compatible, and startup seeding preserves them.

Run the normal launcher after updating: migration `20260922_0023` adds the optional
Bengali-name column without rewriting existing registrations.

### Live updates without constant polling

Live screens use a patient-free WebSocket notification channel and fetch data
through their existing permission-scoped APIs only when relevant data changes.
Changes close together are combined into one refresh, with at most one request
batch running and one follow-up refresh if further changes arrive. Requests have
a 15-second timeout. Reconnecting or returning to a visible tab refreshes current
data, and waiting times advance locally without HTTP requests. Hidden tabs and
settings/report pages do not poll. The fallback checks live screens every 30
seconds only when realtime is unavailable or the last API refresh failed.
WebSocket heartbeats run every 15 seconds to detect a broken connection; these
are not HTTP data refreshes. The server rechecks session access on each heartbeat.

Run the refresh scheduler checks with `node --experimental-strip-types --test
frontend/tests/refresh-scheduler.test.mjs` on Node.js 22.6+ (Node.js 24 recommended).
