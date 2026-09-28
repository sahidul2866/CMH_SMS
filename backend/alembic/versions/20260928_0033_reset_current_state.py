"""Explicit reset to the September 28 room-based application defaults.

Run: alembic -x reset=true upgrade head
Normal upgrades only record this revision; they do not erase records.
The reset runner in env.py bypasses inconsistent older migration history.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa

revision = '20260928_0033'
down_revision = '20260928_0032'
branch_labels = None
depends_on = None


def upgrade():
    # Destructive work is only invoked by the explicit reset runner in env.py.
    pass


def downgrade():
    # A reset cannot restore deleted data.
    pass


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return f'pbkdf2_sha256$600000${salt.hex()}${digest.hex()}'


def reset_database(connection):
    """Rebuild within the caller's transaction; never commit partial work."""
    dialect = connection.dialect.name
    if dialect not in ('sqlite', 'postgresql'):
        raise RuntimeError('Reset supports SQLite and PostgreSQL only')
    if dialect == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_keys').scalar():
        raise RuntimeError('Use alembic -x reset=true upgrade head to reset SQLite with foreign keys safely')
    defaults = json.loads((Path(__file__).parents[1] / 'data' / '20260928_0033_defaults.json').read_text())
    admin = os.getenv('CMH_SMS_ADMIN_USERNAME', 'admin').strip().lower()
    reserved = {'reception', 'radiography_head', 'auditor', 'display', *(room['room_number'] for room in defaults['rooms'])}
    if not re.fullmatch(r'[a-z0-9._-]{2,80}', admin) or admin in reserved:
        raise RuntimeError('CMH_SMS_ADMIN_USERNAME must be a valid, distinct administrator user ID')
    admin_password = os.getenv('CMH_SMS_ADMIN_PASSWORD') or secrets.token_urlsafe(18)
    staff_password = os.getenv('CMH_SMS_SEED_USER_PASSWORD') or secrets.token_urlsafe(18)
    if min(len(admin_password), len(staff_password)) < 10:
        raise RuntimeError('Bootstrap passwords must have at least 10 characters')
    accounts = [dict(username=admin, full_name=os.getenv('CMH_SMS_ADMIN_NAME', 'CMH System Administrator'),
                     role='admin', doctor_id=None, password=admin_password)]
    accounts += [dict(username=role, full_name=role.replace('_', ' ').title(), role=role,
                      doctor_id=None, password=staff_password)
                 for role in ('reception', 'radiography_head', 'auditor', 'display')]
    accounts += [dict(username=room['room_number'], full_name=room['name'], role='radiographer',
                      doctor_id=room['id'], password=staff_password) for room in defaults['rooms']]
    now = datetime.utcnow()
    users = [{key: value for key, value in account.items() if key != 'password'} |
             dict(id=str(uuid5(NAMESPACE_URL, f'cmh-reset-user:{account["username"]}')),
                  password_hash=password_hash(account['password']), must_change_password=True,
                  is_active=True, created_at=now) for account in accounts]
    # Save bootstrap credentials before touching the DB; never print passwords.
    directory = Path(os.getenv('CMH_SMS_RESET_CREDENTIALS_DIR', str(Path(__file__).parents[2] / 'data')))
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix='reset-credentials-', suffix='.json', dir=directory)
    credentials = Path(filename)
    try:
        with os.fdopen(descriptor, 'w') as file:
            json.dump({'revision': revision, 'created_at': now.isoformat(),
                       'accounts': [{'user_id': row['username'], 'temporary_password': row['password']} for row in accounts]}, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        inspector = sa.inspect(connection)
        quote = connection.dialect.identifier_preparer.quote
        cascade = ' CASCADE' if dialect == 'postgresql' else ''
        for view in inspector.get_view_names():
            connection.exec_driver_sql(f'DROP VIEW IF EXISTS {quote(view)}{cascade}')
        if dialect == 'postgresql':
            for view in inspector.get_materialized_view_names():
                connection.exec_driver_sql(f'DROP MATERIALIZED VIEW IF EXISTS {quote(view)} CASCADE')
        # Do not reflect the old schema: missing FK targets and broken columns are allowed.
        for table in inspector.get_table_names():
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS {quote(table)}{cascade}')
        if dialect == 'postgresql':
            # Standalone legacy sequences can collide with new SERIAL columns.
            for sequence in sa.inspect(connection).get_sequence_names():
                connection.exec_driver_sql(f'DROP SEQUENCE IF EXISTS {quote(sequence)} CASCADE')
        for statement in defaults['schema'][dialect]:
            connection.exec_driver_sql(statement)
        metadata = sa.MetaData()
        metadata.reflect(bind=connection)
        def insert(table, rows):
            if rows:
                connection.execute(metadata.tables[table].insert(), rows)
        insert('waiting_rooms', defaults['waiting_rooms'])
        insert('doctors', defaults['rooms'])
        insert('role_definitions', defaults['roles'])
        insert('lookup_options', [row | dict(id=str(uuid5(NAMESPACE_URL, f'cmh-reset-lookup:{row["category"]}:{row["value"]}')),
                                            created_at=now, updated_at=now) for row in defaults['lookups']])
        insert('app_settings', [dict(key=key, value=value, description=f'Current default: {key}', updated_at=now)
                                for key, value in defaults['settings'].items()])
        insert('users', users)
        return credentials
    except BaseException:
        credentials.unlink(missing_ok=True)
        raise
