# CMH Smart Serial

Standalone serial and appointment management product. It borrows the parent HMS's Angular/FastAPI conventions, but has an independent domain, API, UI, and deployment boundary.

## Current vertical slice

- Reception creates a patient token and it joins the doctor's queue immediately.
- Doctor sees a live queue, calls next, or calls a selected patient.
- The waiting-room screen shows the current call and next patients.
- Browser speech synthesis announces patient name, token, doctor, and room in Bangla/English.
- Room-scoped WebSockets push doctor calls to the correct TV immediately; five-second polling remains as automatic recovery.
- Alembic owns the standalone database schema.
- Seed data provides four waiting rooms, four doctors, and realistic live queues.
- The default database is `backend/data/cmh_sms.db`; `CMH_SMS_DATABASE_URL` can point to PostgreSQL.

## Run

macOS/Linux:

```bash
./run.sh
```

Windows (Git Bash, MSYS2, or Cygwin):

```bash
bash run.sh
```

Windows users can alternatively double-click `RUN_WINDOWS.bat`. On Windows,
`run.sh` automatically delegates to that native launcher.

The launcher creates the project-local Python environment, installs dependencies, runs every migration, loads idempotent seed data, and starts both services.
If ports `8100` or `4300` are already occupied, it stops the listening processes before launching the project.

- Application: `http://127.0.0.1:4300`
- API: `http://127.0.0.1:8100`
- API docs: `http://127.0.0.1:8100/docs`

## Database commands

Run from `backend/` after the environment has been created:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
```

Set `CMH_SMS_DATABASE_URL` before `./run.sh` to use an external PostgreSQL database. No HMS database or runtime is used.

For a fresh Windows PC, follow [WINDOWS_SETUP.md](WINDOWS_SETUP.md).
