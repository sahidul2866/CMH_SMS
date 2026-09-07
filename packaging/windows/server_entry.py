from __future__ import annotations

import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path


APP_NAME = "CMH Smart Serial"
PORT = 8100


def bundled_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / relative


def configure_environment() -> tuple[Path, bool]:
    program_data = Path(os.getenv("PROGRAMDATA", Path.home())) / APP_NAME
    data_dir = program_data / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (program_data / "logs").mkdir(exist_ok=True)
    (program_data / "audio-cache").mkdir(exist_ok=True)

    database = data_dir / "cmh_sms.db"
    first_run = not database.exists()
    os.environ.setdefault("CMH_SMS_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    os.environ.setdefault("CMH_SMS_AUDIO_CACHE", str(program_data / "audio-cache"))
    os.environ.setdefault("CMH_SMS_OFFLINE_TTS_MODEL", str(bundled_path("models/mms-tts-ben")))
    os.environ.setdefault("CMH_SMS_FRONTEND_DIST", str(bundled_path("frontend")))
    os.environ.setdefault("CMH_SMS_ALLOWED_HOSTS", "*")
    os.environ.setdefault("CMH_SMS_ENVIRONMENT", "development")
    os.environ.setdefault("CMH_SMS_AUDIO_ENABLED", "true")
    os.environ.setdefault("CMH_SMS_COOKIE_SECURE", "false")

    if first_run:
        password = secrets.token_hex(10)
        os.environ["CMH_SMS_ADMIN_USERNAME"] = "admin"
        os.environ["CMH_SMS_ADMIN_PASSWORD"] = password
        credential_file = program_data / "INITIAL_ADMIN_LOGIN.txt"
        credential_file.write_text(f"Username: admin\nInitial password: {password}\n", encoding="utf-8")
    return program_data, first_run


def migrate_and_seed() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(bundled_path("alembic.ini")))
    config.set_main_option("script_location", str(bundled_path("alembic")))
    config.set_main_option("sqlalchemy.url", os.environ["CMH_SMS_DATABASE_URL"].replace("%", "%%"))
    command.upgrade(config, "head")

    from app.seed import seed

    seed()


def open_browser() -> None:
    time.sleep(3)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main() -> None:
    program_data, first_run = configure_environment()
    migrate_and_seed()
    if first_run:
        os.startfile(program_data / "INITIAL_ADMIN_LOGIN.txt")
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    from app.main import app

    while True:
        try:
            uvicorn.run(app, host="0.0.0.0", port=PORT, access_log=False)
        except Exception as exc:
            with (program_data / "logs" / "server-errors.log").open("a", encoding="utf-8") as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {exc!r}\n")
        time.sleep(10)


if __name__ == "__main__":
    main()
