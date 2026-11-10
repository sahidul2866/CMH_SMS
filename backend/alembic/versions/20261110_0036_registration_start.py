"""Archive patient activity once and restart 2026 entries at 12130/26."""
from alembic import op
import sqlalchemy as sa

revision = '20261110_0036'
down_revision = '20261005_0035'
branch_labels = None
depends_on = None

# Child tables precede parents for deletion. History copies retain original IDs.
ACTIVITY_TABLES = (
    'call_events', 'audit_events', 'sms_messages', 'queue_tokens',
    'appointments', 'patients', 'registration_counters',
)
HISTORY_PREFIX = 'history_20261110_0036_'


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == 'sqlite':
        # SQLite's legacy transaction mode otherwise auto-commits the archive DDL.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    elif connection.dialect.name == 'postgresql':
        connection.exec_driver_sql(
            'LOCK TABLE ' + ', '.join((*ACTIVITY_TABLES, 'device_endpoints')) +
            ' IN ACCESS EXCLUSIVE MODE'
        )
    else:
        raise RuntimeError('Patient archiving supports PostgreSQL and SQLite only')

    quote = connection.dialect.identifier_preparer.quote
    # Copy every column, including any deployment-specific fields, before deleting.
    # Snapshot tables deliberately have no foreign keys to the active tables.
    for name in ACTIVITY_TABLES:
        history = HISTORY_PREFIX + name
        connection.exec_driver_sql(
            f'CREATE TABLE {quote(history)} AS SELECT * FROM {quote(name)}'
        )
        old_count = connection.scalar(sa.text(f'SELECT COUNT(*) FROM {quote(name)}'))
        saved_count = connection.scalar(sa.text(f'SELECT COUNT(*) FROM {quote(history)}'))
        if old_count != saved_count:
            raise RuntimeError(f'Archive verification failed for {name}')

    for name in ACTIVITY_TABLES:
        connection.exec_driver_sql(f'DELETE FROM {quote(name)}')
    connection.exec_driver_sql(
        'UPDATE device_endpoints SET last_event_id = NULL, last_acknowledged_event_id = NULL'
    )
    connection.exec_driver_sql(
        'INSERT INTO registration_counters (year, sequence) VALUES (2026, 12129)'
    )


def downgrade():
    raise RuntimeError('This archive migration cannot be reversed automatically; history tables are retained.')
