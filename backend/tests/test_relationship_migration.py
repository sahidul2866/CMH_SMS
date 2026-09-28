import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AppSetting, LookupOption


def test_relationship_migration_replaces_choices_without_changing_saved_mappings():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20260928_0031_patient_relationships.py'
    spec = importlib.util.spec_from_file_location('relationships_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LookupOption(id='legacy', category='family_relationship', value='spouse', label='Spouse'))
        db.add(AppSetting(key='mri_summary_mapping', description='Test mapping', value={'re': None, 'military:family:serving:officer': 'family_officer'}))
        db.commit()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
    with Session(engine) as db:
        choices = db.scalars(select(LookupOption).where(LookupOption.category == 'family_relationship', LookupOption.is_active.is_(True))).all()
        assert len(choices) == 8
        assert {row.label for row in choices} == {'DAUGHTER', 'SON', 'WIFE', 'HUSBAND', 'MOTHER', 'FATHER', 'MOTHER IN LAW', 'FATHER IN LAW'}
        assert not db.get(LookupOption, 'legacy').is_active
        assert db.get(LookupOption, 'legacy').label == 'Spouse'
        assert db.get(AppSetting, 'mri_summary_mapping').value == {'re': None, 'military:family:serving:officer': 'family_officer'}
    engine.dispose()
