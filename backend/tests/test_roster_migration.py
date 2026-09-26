import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Doctor, LookupOption, User, WaitingRoom


def test_roster_migration_preserves_ids_accounts_and_custom_rooms():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20260926_0024_radiographer_directory.py'
    spec = importlib.util.spec_from_file_location('roster_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(WaitingRoom(id='wr', code='WR', name='Waiting', floor='1', display_label='Waiting'))
        db.flush()
        for doctor_id, old_name, old_room, _, _ in migration.ROSTER:
            db.add(Doctor(id=doctor_id, name=old_name, room_number=old_room, department='Radiology', designation='Radiographer', waiting_room_id='wr', token_prefix=doctor_id))
        db.flush()
        db.add(User(id='staff', username='radiographer', full_name='Dr. Ayesha Khan', password_hash='unchanged', role='radiographer', doctor_id='dr-khan'))
        db.add(LookupOption(id='existing-room', category='room_number', value='110', label='Existing room label', metadata_json={}))
        db.commit()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()  # Existing room choices must not be duplicated.
    with Session(engine) as db:
        for doctor_id, _, _, name, room in migration.ROSTER:
            doctor = db.get(Doctor, doctor_id)
            assert (doctor.name, doctor.room_number, doctor.waiting_room_id) == (name, room, 'wr')
        user = db.get(User, 'staff')
        assert (user.full_name, user.username, user.password_hash, user.doctor_id) == ('SWO Jamil Ahmed', 'radiographer', 'unchanged', 'dr-khan')
        rooms = db.scalars(select(LookupOption).where(LookupOption.category == 'room_number')).all()
        assert {room.value for room in rooms} == {'110', '116', '104', '117'}
        assert len(rooms) == 4
        assert db.get(LookupOption, 'existing-room').label == 'Existing room label'
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
    with Session(engine) as db:
        assert db.get(Doctor, 'dr-khan').name == 'Dr. Ayesha Khan'
        assert db.get(Doctor, 'dr-khan').room_number == '205'
        assert db.get(User, 'staff').full_name == 'Dr. Ayesha Khan'
    engine.dispose()
