import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_migration_adds_reports_to_builtin_radiographer_without_overwriting_other_roles():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261005_0035_radiographer_reports.py'
    spec = importlib.util.spec_from_file_location('radiographer_reports_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    roles = sa.Table(
        'role_definitions', metadata,
        sa.Column('name', sa.String, primary_key=True),
        sa.Column('access_profile', sa.String),
        sa.Column('permissions', sa.JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(roles.insert(), [
            {
                'name': 'radiographer',
                'access_profile': 'radiographer',
                'permissions': ['custom.permission', 'queue.view'],
            },
            {
                'name': 'custom_technologist',
                'access_profile': 'radiographer',
                'permissions': ['queue.view'],
            },
        ])
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        permissions = {
            row.name: row.permissions
            for row in connection.execute(sa.select(roles.c.name, roles.c.permissions))
        }
        assert permissions['radiographer'] == [
            'custom.permission', 'pages.reports', 'queue.view', 'reports.view',
        ]
        assert permissions['custom_technologist'] == ['queue.view']
    engine.dispose()
