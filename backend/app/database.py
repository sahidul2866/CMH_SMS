from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
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

    primary_engine = create_engine(primary_url, pool_pre_ping=True)
    sqlite_engine = create_engine(
        replica_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    Base.metadata.create_all(bind=sqlite_engine)
    with primary_engine.connect() as source_conn:
        for table in Base.metadata.sorted_tables:
            rows = source_conn.execute(select(table)).mappings().all()
            with sqlite_engine.begin() as target_conn:
                target_conn.execute(table.delete())
                if rows:
                    target_conn.execute(table.insert(), rows)

    primary_engine.dispose()
    sqlite_engine.dispose()
    return replica_url


DATABASE_URL = _resolve_database_url()
REPLICA_DATABASE_URL = _ensure_sqlite_replica(DATABASE_URL, _replica_database_url())
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
