from logging.config import fileConfig

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from sqlalchemy import engine_from_config, pool

from alembic import context
from app import models  # noqa: F401
from app.database import DATABASE_URL, Base

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    if context.get_x_argument(as_dictionary=True).get('reset'):
        raise RuntimeError('Database reset requires an online connection')
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_reset(connection):
    script = ScriptDirectory.from_config(config)
    migration = script.get_revision('20260928_0033').module
    sqlite = connection.dialect.name == 'sqlite'
    foreign_keys = None
    if sqlite:
        foreign_keys = connection.exec_driver_sql('PRAGMA foreign_keys').scalar()
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        connection.commit()
    credentials = None
    try:
        with connection.begin():
            if sqlite:
                # SQLite otherwise autocommits DDL before its first data write.
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            credentials = migration.reset_database(connection)
            version = sa.Table('alembic_version', sa.MetaData(),
                               sa.Column('version_num', sa.String(32), primary_key=True))
            version.create(connection)
            connection.execute(version.insert().values(version_num=migration.revision))
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        print(f'Database reset complete. Temporary login credentials: {credentials}')
    except BaseException:
        if credentials:
            credentials.unlink(missing_ok=True)
        raise
    finally:
        if sqlite:
            connection.exec_driver_sql(f'PRAGMA foreign_keys={1 if foreign_keys else 0}')
            connection.commit()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if context.get_x_argument(as_dictionary=True).get('reset', '').lower() in ('true', '1', 'yes'):
            run_reset(connection)
            return
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
