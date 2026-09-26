"""PostgreSQL bootstrap and shared environment for Windows source launchers."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.setup' / 'postgres.json'


def validate_url(value: str) -> str:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError('Invalid PostgreSQL URL; check the connection configuration.') from None
    if url.drivername not in ('postgresql', 'postgresql+psycopg'):
        raise ValueError('Windows requires a PostgreSQL URL; SQLite is not supported by this launcher.')
    if not url.database or not url.username:
        raise ValueError('The PostgreSQL URL must specify a database and user.')
    return url.set(drivername='postgresql+psycopg').render_as_string(hide_password=False)


def connect(value: str):
    url = make_url(validate_url(value))
    options = dict(url.query)
    options.update(host=url.host or '127.0.0.1', port=url.port or 5432,
                   user=url.username, password=url.password, dbname=url.database,
                   connect_timeout=10)
    return psycopg.connect(**options, autocommit=True)


def save_config(config: dict) -> None:
    CONFIG.parent.mkdir(exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    if os.name == 'nt':
        # Limit credentials to this account, SYSTEM and local administrators.
        identity = subprocess.check_output(['whoami'], text=True).strip()
        subprocess.run(['icacls', str(temporary), '/inheritance:r', '/grant:r',
                        f'{identity}:F', '*S-1-5-18:F', '*S-1-5-32-544:F'],
                       check=True, stdout=subprocess.DEVNULL)
    else:
        temporary.chmod(0o600)
    temporary.replace(CONFIG)


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}


def provision(config: dict) -> None:
    print('Enter the PostgreSQL postgres administrator password chosen during installation.')
    admin_password = getpass.getpass('PostgreSQL administrator password: ')
    try:
        administrator = psycopg.connect(host='127.0.0.1', port=5432, dbname='postgres',
                                       user='postgres', password=admin_password,
                                       connect_timeout=10, autocommit=True)
    except psycopg.errors.InvalidPassword:
        raise ValueError('PostgreSQL rejected the postgres administrator password on 127.0.0.1:5432. '
                         'CMH setup has not changed it. Check that this is the intended PostgreSQL instance.') from None
    except psycopg.Error:
        raise ValueError('Could not connect as postgres on 127.0.0.1:5432. '
                         'Check the PostgreSQL service, port and local authentication rules.') from None
    with administrator as admin:
        exists = admin.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', ('cmh_sms',)).fetchone()
        if not exists:
            password = make_url(config['url']).password
            admin.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}')
                          .format(sql.Identifier('cmh_sms'), sql.Literal(password)))
        # Never reset the password of a pre-existing role.
        probe = make_url(config['url']).set(database='postgres').render_as_string(hide_password=False)
        try:
            with connect(probe) as app:
                app.execute('SELECT 1')
        except psycopg.errors.InvalidPassword:
            raise ValueError('Administrator login succeeded, but the saved cmh_sms application password was rejected. '
                             'Restore .setup/postgres.json from the original installation, or configure '
                             'CMH_SMS_DATABASE_URL with the existing application credentials. '
                             'Do not delete the database or reset the postgres administrator password for this error.') from None
        exists = admin.execute('SELECT 1 FROM pg_database WHERE datname = %s', ('cmh_sms',)).fetchone()
        if not exists:
            admin.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(
                sql.Identifier('cmh_sms'), sql.Identifier('cmh_sms')))


def setup() -> None:
    config = load_config()
    resuming = bool(config)
    supplied = os.getenv('CMH_SMS_DATABASE_URL')
    if supplied:
        candidate = {'url': validate_url(supplied), 'managed_local': False}
        with connect(candidate['url']) as conn:
            conn.execute('SELECT 1')
        save_config(candidate)
        print('Configured existing PostgreSQL database.')
        return
    if not config:
        if (ROOT / 'backend' / 'data' / 'cmh_sms.db').exists():
            print('NOTICE: Existing backend/data/cmh_sms.db is preserved and will not be used. '
                  'Continuing with PostgreSQL setup. SQLite records are not imported; '
                  'restore a PostgreSQL backup or arrange migration if you need existing records.')
        password = secrets.token_hex(24)
        config = {'url': f'postgresql+psycopg://cmh_sms:{password}@127.0.0.1:5432/cmh_sms',
                  'managed_local': True, 'provisioned': False}
        # Persist before provisioning so a failed/interrupted setup can resume safely.
        save_config(config)
    config['url'] = validate_url(config['url'])
    if config.get('managed_local'):
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                        '-File', str(ROOT / 'scripts' / 'ensure_postgres_windows.ps1')], check=True)
        if not config.get('provisioned'):
            ready = False
            if resuming:
                try:
                    with connect(config['url']) as conn:
                        conn.execute('SELECT 1')
                    ready = True
                except psycopg.Error:
                    pass
            if not ready:
                provision(config)
    with connect(config['url']) as conn:
        conn.execute('SELECT 1')
    config['provisioned'] = True
    save_config(config)
    print('PostgreSQL is ready. Existing databases and passwords are preserved.')


def environment() -> dict[str, str]:
    config = load_config()
    value = os.getenv('CMH_SMS_DATABASE_URL') or config.get('url')
    if not value:
        raise ValueError('PostgreSQL is not configured. Run RUN_WINDOWS.bat first.')
    env = dict(os.environ)
    env['CMH_SMS_DATABASE_URL'] = validate_url(value)
    env['CMH_SMS_DATABASE_MODE'] = 'postgres'
    # A copied .env may point the optional snapshot at a legacy database.
    # Windows source launchers use PostgreSQL only and preserve SQLite files.
    env['CMH_SMS_SQLITE_REPLICA'] = 'false'
    return env


def main() -> int:
    try:
        if sys.argv[1:] == ['--setup']:
            setup()
            return 0
        env = environment()
        with connect(env['CMH_SMS_DATABASE_URL']) as conn:
            conn.execute('SELECT 1')
        if sys.argv[1:] == ['--check']:
            return 0
        if len(sys.argv) < 2:
            raise ValueError('Specify --setup, --check, or a Python module to run.')
        return subprocess.call([sys.executable, '-m', *sys.argv[1:]],
                               cwd=ROOT / 'backend', env=env)
    except ValueError as exc:
        # Do not echo URL parsing errors, which may contain credentials.
        if type(exc) is ValueError:
            print(f'ERROR: {exc}', file=sys.stderr)
        else:
            print('ERROR: Invalid PostgreSQL configuration.', file=sys.stderr)
        return 1
    except psycopg.errors.InvalidPassword:
        print('ERROR: The saved application database credentials were rejected. '
              'The postgres administrator password was not changed. Restore the original .setup/postgres.json '
              'or set CMH_SMS_DATABASE_URL to valid existing credentials.', file=sys.stderr)
        return 1
    except (psycopg.Error, subprocess.CalledProcessError, OSError):
        print('ERROR: PostgreSQL setup/connection failed. Check the service, credentials and database access. '
              'Existing roles are not reset; for an existing database set CMH_SMS_DATABASE_URL. '
              'No SQLite fallback was used.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
