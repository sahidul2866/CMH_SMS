from __future__ import annotations

import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'cmh_sms.db'}"
DEFAULT_REPLICA_SQLITE_URL = f"sqlite:///{DATA_DIR / 'cmh_sms_replica.db'}"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sqlite_url(path: str | None = None) -> str:
    if path:
        sqlite_path = Path(path).expanduser()
    else:
        sqlite_path = DATA_DIR / "cmh_sms_replica.db"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path.as_posix()}"


def _resolve_database_url() -> str:
    requested_mode = os.getenv("CMH_SMS_DATABASE_MODE", "postgres").strip().lower()
    requested_url = os.getenv("CMH_SMS_DATABASE_URL")

    if requested_mode == "sqlite":
        chosen_url = requested_url or DEFAULT_SQLITE_URL
        os.environ["CMH_SMS_DATABASE_URL"] = chosen_url
        return chosen_url

    if requested_url and requested_url.startswith("postgresql"):
        os.environ["CMH_SMS_DATABASE_URL"] = requested_url
        return requested_url

    chosen_url = requested_url or DEFAULT_SQLITE_URL
    os.environ["CMH_SMS_DATABASE_URL"] = chosen_url
    return chosen_url


class Base(DeclarativeBase):
    pass


def _replica_database_url() -> str | None:
    if not _as_bool(os.getenv("CMH_SMS_SQLITE_REPLICA"), False):
        return None
    requested_path = os.getenv("CMH_SMS_SQLITE_REPLICA_PATH")
    return _sqlite_url(requested_path or str(DATA_DIR / "cmh_sms_replica.db"))


def _ensure_sqlite_replica(primary_url: str, replica_url: str | None) -> str | None:
    if replica_url is None or not primary_url.startswith("postgresql"):
        return None

    from sqlalchemy import select

    from . import models  # noqa: F401

    destination = Path(make_url(replica_url).database).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # This is a derived startup snapshot, not the primary database. Build a fresh
    # schema beside it and replace only after every table has copied successfully.
    with tempfile.NamedTemporaryFile(prefix=destination.name + '.', suffix='.tmp', dir=destination.parent, delete=False) as staging:
        temporary = Path(staging.name)
    primary_engine = None
    sqlite_engine = None
    try:
        primary_engine = create_engine(primary_url, pool_pre_ping=True, hide_parameters=True,
                                       isolation_level='REPEATABLE READ')
        sqlite_engine = create_engine(f'sqlite:///{temporary.as_posix()}', hide_parameters=True)
        Base.metadata.create_all(bind=sqlite_engine)
        with primary_engine.connect() as source_conn, source_conn.begin(), sqlite_engine.begin() as target_conn:
            for table in Base.metadata.sorted_tables:
                for rows in source_conn.execute(select(table)).mappings().partitions(1000):
                    target_conn.execute(table.insert(), rows)
        sqlite_engine.dispose()
        primary_engine.dispose()
        temporary.replace(destination)
    finally:
        if sqlite_engine is not None:
            sqlite_engine.dispose()
        if primary_engine is not None:
            primary_engine.dispose()
        temporary.unlink(missing_ok=True)
    return replica_url


def refresh_sqlite_replica() -> None:
    """Called at application startup, after the launcher applies migrations."""
    _ensure_sqlite_replica(DATABASE_URL, REPLICA_DATABASE_URL)


DATABASE_URL = _resolve_database_url()
REPLICA_DATABASE_URL = _replica_database_url() if DATABASE_URL.startswith("postgresql") else None
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=1800 if not DATABASE_URL.startswith("sqlite") else -1,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
