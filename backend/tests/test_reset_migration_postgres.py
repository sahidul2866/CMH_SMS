"""Optional integration test using its own temporary PostgreSQL server."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import shlex

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not shutil.which('initdb') or not shutil.which('pg_ctl') or (hasattr(os, 'geteuid') and os.geteuid() == 0), reason='Requires PostgreSQL tools and a non-root user')
def test_reset_postgres_with_invalid_history_duplicates_and_rollback():
    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='cmh-reset-pg-', dir='/tmp') as temporary:
        root = Path(temporary)
        database, sockets = root / 'database', root / 'socket'
        sockets.mkdir()
        init = subprocess.run(['initdb', '-D', str(database), '-A', 'trust', '-U', 'postgres', '--no-locale', '-E', 'UTF8'], capture_output=True, text=True, timeout=30)
        assert init.returncode == 0, init.stderr
        # Only a private Unix socket; no listener on the user's network.
        options = shlex.join(['-k', str(sockets), '-h', '', '-p', '55439'])
        start = subprocess.run(['pg_ctl', '-D', str(database), '-l', str(root / 'postgres.log'), '-o', options, '-w', 'start'], capture_output=True, text=True, timeout=30)
        assert start.returncode == 0, start.stderr
        url = f'postgresql+psycopg://postgres@/postgres?host={sockets}&port=55439'
        engine = create_engine(url)
        try:
            with engine.begin() as db:
                db.execute(text('CREATE TABLE alembic_version (version_num text)'))
                db.execute(text("INSERT INTO alembic_version VALUES ('missing-revision')"))
                db.execute(text('CREATE SEQUENCE registration_counters_year_seq'))
                db.execute(text('CREATE TABLE users (username text)'))
                db.execute(text("INSERT INTO users VALUES ('110'), ('110')"))
                db.execute(text('CREATE VIEW legacy_view AS SELECT * FROM users'))
                db.execute(text('CREATE TABLE child (id int PRIMARY KEY, parent int REFERENCES child(id))'))
            environment = {**os.environ, 'CMH_SMS_DATABASE_URL': url, 'CMH_SMS_SQLITE_REPLICA': 'false',
                           'CMH_SMS_ADMIN_USERNAME': 'admin', 'CMH_SMS_ADMIN_PASSWORD': 'PostgresAdmin123!',
                           'CMH_SMS_SEED_USER_PASSWORD': 'PostgresStaff123!', 'CMH_SMS_RESET_CREDENTIALS_DIR': str(root / 'credentials')}
            command = [sys.executable, '-m', 'alembic', '-x', 'reset=true', 'upgrade']
            for _ in range(2):
                reset = subprocess.run([*command, 'head'], cwd=backend, env=environment, capture_output=True, text=True, timeout=60)
                assert reset.returncode == 0, reset.stdout + reset.stderr
                with engine.connect() as db:
                    assert set(db.execute(text("SELECT username FROM users WHERE role='radiographer'")).scalars()) == {'110', '104', '116', '117'}
                    radiographer_permissions = db.execute(text(
                        "SELECT permissions FROM role_definitions WHERE name='radiographer'"
                    )).scalar_one()
                    assert {'pages.reports', 'reports.view'} <= set(radiographer_permissions)
                    assert db.execute(text('SELECT count(*) FROM queue_tokens')).scalar() == 0
                    assert db.execute(text('SELECT version_num FROM alembic_version')).scalar() == '20261005_0035'
            with engine.begin() as db:
                db.execute(text("CREATE TABLE retained_on_failure (value text)"))
                db.execute(text("INSERT INTO retained_on_failure VALUES ('keep')"))
                before = dict(db.execute(text('SELECT username, password_hash FROM users')).all())
            failed = subprocess.run([*command, 'unknown-target'], cwd=backend, env=environment, capture_output=True, text=True, timeout=60)
            assert failed.returncode != 0
            with engine.connect() as db:
                assert db.execute(text('SELECT value FROM retained_on_failure')).scalar() == 'keep'
                assert dict(db.execute(text('SELECT username, password_hash FROM users')).all()) == before
            assert len(list((root / 'credentials').glob('*.json'))) == 2
        finally:
            engine.dispose()
            subprocess.run(['pg_ctl', '-D', str(database), '-m', 'immediate', '-w', 'stop'], capture_output=True, timeout=30, check=True)
