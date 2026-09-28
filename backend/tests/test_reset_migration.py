"""Exercise reset using disposable databases only."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

BACKEND = Path(__file__).resolve().parents[1]


def run_reset(path, directory, *arguments, **extra):
    environment = {**os.environ, 'CMH_SMS_DATABASE_URL': f'sqlite:///{path}',
                   'CMH_SMS_RESET_CREDENTIALS_DIR': str(directory),
                   'CMH_SMS_ADMIN_USERNAME': 'admin', 'CMH_SMS_ADMIN_NAME': 'Administrator',
                   'CMH_SMS_ADMIN_PASSWORD': 'AdminReset123!', 'CMH_SMS_SEED_USER_PASSWORD': 'StaffReset123!'}
    environment.update(extra)
    return subprocess.run([sys.executable, '-m', 'alembic', '-x', 'reset=true', 'upgrade', *(arguments or ('head',))],
                          cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=60)


def verify_defaults(path):
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [('20260928_0034',)]
        assert set(db.execute('SELECT room_number, name FROM doctors')) == {(n, f'Room {n}') for n in ('110', '104', '116', '117')}
        assert set(db.execute("SELECT username FROM users WHERE role='radiographer'")) == {(n,) for n in ('110', '104', '116', '117')}
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 9
        assert db.execute('SELECT count(*) FROM users WHERE must_change_password=1').fetchone()[0] == 9
        assert set(db.execute("SELECT value FROM lookup_options WHERE category='family_relationship'")) == {(n,) for n in ('daughter','son','wife','husband','mother','father','mother_in_law','father_in_law')}
        for table in ('queue_tokens', 'patients', 'appointments', 'schedule_slots', 'audit_events', 'user_sessions', 'sms_messages', 'call_events', 'registration_counters'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        mappings = json.loads(db.execute("SELECT value FROM app_settings WHERE key='mri_summary_mapping'").fetchone()[0])
        assert mappings['re'] == 're' and mappings['cne'] == 'cne'
        assert mappings['military:family:serving:officer'] == 'family_officer'
        return dict(db.execute('SELECT username, password_hash FROM users'))


@pytest.mark.parametrize('situation', ['empty', 'broken_history', 'partial_schema', 'orphaned_foreign_keys'])
def test_reset_rebuilds_existing_sqlite_states(tmp_path, situation):
    path = tmp_path / 'reset.db'
    with sqlite3.connect(path) as db:
        if situation == 'broken_history':
            db.executescript("CREATE TABLE alembic_version (wrong_column TEXT); INSERT INTO alembic_version VALUES ('unknown'); CREATE TABLE users (username TEXT); INSERT INTO users VALUES ('110'), ('110');")
        elif situation == 'partial_schema':
            db.executescript("CREATE TABLE alembic_version (version_num TEXT); INSERT INTO alembic_version VALUES ('unknown_revision'); CREATE TABLE queue_tokens (obsolete TEXT); INSERT INTO queue_tokens VALUES ('old patient'); CREATE VIEW stale_view AS SELECT * FROM missing_table;")
        elif situation == 'orphaned_foreign_keys':
            db.executescript("CREATE TABLE legacy (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES missing_table(id)); INSERT INTO legacy VALUES (1,99);")
    result = run_reset(path, tmp_path / 'credentials')
    assert result.returncode == 0, result.stdout + result.stderr
    before = verify_defaults(path)
    credentials = list((tmp_path / 'credentials').glob('*.json'))
    assert len(credentials) == 1
    assert credentials[0].stat().st_mode & 0o077 == 0
    assert 'AdminReset123!' not in result.stdout + result.stderr
    environment = {**os.environ, 'CMH_SMS_DATABASE_URL': f'sqlite:///{path}'}
    normal = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=60)
    assert normal.returncode == 0, normal.stderr
    assert verify_defaults(path) == before


def test_reset_repeats_and_generates_missing_credentials(tmp_path):
    path = tmp_path / 'repeat.db'
    for _ in range(2):
        result = run_reset(path, tmp_path / 'credentials', CMH_SMS_ADMIN_PASSWORD='', CMH_SMS_SEED_USER_PASSWORD='')
        assert result.returncode == 0, result.stderr
        verify_defaults(path)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE obsolete (value TEXT)')
            db.execute("INSERT INTO obsolete VALUES ('remove me')")
    files = list((tmp_path / 'credentials').glob('*.json'))
    assert len(files) == 2
    for file in files:
        assert all(len(account['temporary_password']) >= 10 for account in json.loads(file.read_text())['accounts'])


def test_failure_rolls_back_schema_and_records(tmp_path):
    path = tmp_path / 'rollback.db'
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE precious (value TEXT); INSERT INTO precious VALUES ('original');")
    result = run_reset(path, tmp_path / 'credentials', 'not_a_revision')
    assert result.returncode != 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT value FROM precious').fetchall() == [('original',)]
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('precious',)]
    assert not list((tmp_path / 'credentials').glob('*.json'))
