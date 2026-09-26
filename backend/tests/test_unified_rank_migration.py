import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_unified_rank_migrates_family_aliases_and_preserves_other_ranks_and_policies():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20260926_0026_unified_rank.py'
    spec = importlib.util.spec_from_file_location('rank_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    tokens = sa.Table('queue_tokens', metadata, sa.Column('id', sa.Integer, primary_key=True), sa.Column('rank', sa.String(60)), sa.Column('sponsor_rank', sa.String(100)), sa.Column('beneficiary_type', sa.String), sa.Column('summary_category', sa.String))
    settings = sa.Table('app_settings', metadata, sa.Column('key', sa.String, primary_key=True), sa.Column('value', sa.JSON))
    options = sa.Table('lookup_options', metadata, sa.Column('category', sa.String), sa.Column('value', sa.String), sa.Column('metadata_json', sa.JSON))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(options.insert(), {'category': 'beneficiary_type', 'value': 'dependent', 'metadata_json': {'report_code': 'family'}})
        conn.execute(tokens.insert(), [
            {'id': 1, 'rank': None, 'sponsor_rank': 'major', 'beneficiary_type': 'family', 'summary_category': 'saved-category'},
            {'id': 2, 'rank': 'captain', 'sponsor_rank': 'major', 'beneficiary_type': 'self', 'summary_category': None},
            {'id': 3, 'rank': '', 'sponsor_rank': 'x' * 100, 'beneficiary_type': 'dependent', 'summary_category': None},
            {'id': 4, 'rank': 'sergeant', 'sponsor_rank': None, 'beneficiary_type': 'family', 'summary_category': None},
        ])
        conn.execute(settings.insert(), {'key': 'registration_fields', 'value': {'required': ['patient_name', 'sponsor_rank'], 'enabled': ['patient_name', 'rank', 'sponsor_rank'], 'custom': []}})
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        columns = {item['name']: item for item in sa.inspect(conn).get_columns('queue_tokens')}
        assert 'sponsor_rank' not in columns
        assert columns['rank']['type'].length == 100
        rows = conn.execute(sa.text('select id, rank, summary_category from queue_tokens order by id')).all()
        assert [row.rank for row in rows] == ['major', 'captain', 'x' * 100, 'sergeant']
        assert rows[0].summary_category == 'saved-category'
        config = conn.execute(sa.select(settings.c.value)).scalar_one()
        assert config['required'] == ['patient_name', 'rank']
        assert config['enabled'] == ['patient_name', 'rank']
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert conn.execute(sa.text('select sponsor_rank from queue_tokens where id=1')).scalar_one() == 'major'
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    engine.dispose()
