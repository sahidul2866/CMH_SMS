import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_verification_migration_preserves_entries_and_grants_default_roles_only():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261111_0037_report_verification.py'
    spec = importlib.util.spec_from_file_location('verification_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    tokens = sa.Table('queue_tokens', metadata, sa.Column('id', sa.String, primary_key=True), sa.Column('serial_number', sa.String))
    roles = sa.Table('role_definitions', metadata, sa.Column('name', sa.String, primary_key=True), sa.Column('permissions', sa.JSON))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(tokens.insert().values(id='existing', serial_number='12130/26'))
        connection.execute(roles.insert(), [{'name': name, 'permissions': ['custom.permission']} for name in ['admin', 'radiographer', 'reception']])
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        row = connection.execute(sa.text('SELECT serial_number, report_verified FROM queue_tokens')).one()
        assert row == ('12130/26', 0)
        permissions = dict(connection.execute(sa.select(roles)).all())
        assert 'reports.verify' in permissions['admin']
        assert 'reports.verify' in permissions['radiographer']
        assert permissions['reception'] == ['custom.permission']
