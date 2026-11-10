"""Startup upgrades must never reset an already-issued entry serial."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_startup_applies_serial_start_only_once(tmp_path):
    database = tmp_path / 'startup.db'
    with sqlite3.connect(database) as connection:
        connection.executescript('''
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
            INSERT INTO alembic_version VALUES ('20261005_0035');
            CREATE TABLE registration_counters (year INTEGER PRIMARY KEY, sequence INTEGER NOT NULL);
            INSERT INTO registration_counters VALUES (2026, 12);
            CREATE TABLE patients (id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE appointments (id TEXT PRIMARY KEY);
            CREATE TABLE queue_tokens (id TEXT PRIMARY KEY);
            CREATE TABLE call_events (id TEXT PRIMARY KEY);
            CREATE TABLE audit_events (id TEXT PRIMARY KEY);
            CREATE TABLE sms_messages (id TEXT PRIMARY KEY);
            CREATE TABLE device_endpoints (id TEXT PRIMARY KEY, last_event_id TEXT, last_acknowledged_event_id TEXT);
            INSERT INTO patients VALUES ('existing', 'Existing patient');
        ''')
    environment = {**os.environ, 'CMH_SMS_DATABASE_MODE': 'sqlite',
                   'CMH_SMS_DATABASE_URL': f'sqlite:///{database}'}
    def startup():
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                       cwd=Path(__file__).resolve().parents[1], env=environment,
                       check=True, capture_output=True, text=True, timeout=30)
    startup()
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT sequence FROM registration_counters').fetchone() == (12129,)
        # Two entries have now been issued.
        connection.execute('UPDATE registration_counters SET sequence=12131')
    startup()
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT sequence FROM registration_counters').fetchone() == (12131,)
        assert connection.execute('SELECT id FROM patients').fetchall() == []
        assert connection.execute('SELECT id FROM history_20261110_0036_patients').fetchall() == [('existing',)]
        assert connection.execute('SELECT sequence FROM history_20261110_0036_registration_counters').fetchone() == (12,)
