import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal
from app.models import Doctor, RoleDefinition, User, WaitingRoom
from test_queue import client, setup_function  # noqa: F401


def install_role():
    with SessionLocal() as db:
        db.add(RoleDefinition(name='radiographer', display_name='Radiographer', access_profile='radiographer', permissions=[]))
        db.commit()


def test_radiographer_ids_use_room_number_and_passwords_work():
    install_role()
    for expected in ('205',):
        response = client.post('/api/v1/users', json={'role': 'radiographer', 'doctor_id': 'dr-khan', 'password': 'RoomPass123!'})
        assert response.status_code == 201, response.text
        assert response.json()['username'] == expected
        assert response.json()['full_name'] == 'Room 205'
    duplicate = client.post('/api/v1/users', json={'role': 'radiographer', 'doctor_id': 'dr-khan', 'password': 'RoomPass123!'})
    assert duplicate.status_code == 409
    login = client.post('/api/v1/auth/login', json={'username': '205', 'password': 'RoomPass123!'})
    assert login.status_code == 200
    assert login.json()['username'] == '205'


def test_room_reassignment_and_renumbering_preserve_password():
    install_role()
    with SessionLocal() as db:
        db.add(Doctor(id='other-room', name='Room 7', room_number='7', department='Radiology', designation='Room',
                      waiting_room_id='waiting-room-1', token_prefix='R7'))
        db.commit()
    created = client.post('/api/v1/users', json={'username': 'ignored-name', 'role': 'radiographer',
        'doctor_id': 'dr-khan', 'password': 'RoomPass123!'}).json()
    moved = client.patch(f"/api/v1/users/{created['id']}", json={'doctor_id': 'other-room'})
    assert moved.status_code == 200, moved.text
    assert moved.json()['username'] == '7'
    assert moved.json()['full_name'] == 'Room 7'
    renamed = client.patch('/api/v1/admin/doctors/other-room', json={'room_number': '8'})
    assert renamed.status_code == 200, renamed.text
    assert client.post('/api/v1/auth/login', json={'username': '8', 'password': 'RoomPass123!'}).status_code == 200
    assert client.post('/api/v1/auth/login', json={'username': '7', 'password': 'RoomPass123!'}).status_code == 401


def test_room_id_collision_and_non_room_account_validation():
    install_role()
    with SessionLocal() as db:
        db.add(User(username='205', full_name='Other account', role='admin', password_hash='untouched'))
        db.add(RoleDefinition(name='reception', display_name='Reception', access_profile='reception', permissions=[]))
        db.commit()
    created = client.post('/api/v1/users', json={'role': 'radiographer', 'doctor_id': 'dr-khan', 'password': 'RoomPass123!'})
    assert created.status_code == 409
    assert client.post('/api/v1/users', json={'role': 'reception', 'password': 'RoomPass123!'}).status_code == 422


def test_migration_preserves_account_identity_credentials_and_custom_roles():
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20260928_0032_room_user_ids.py'
    spec = importlib.util.spec_from_file_location('room_user_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(WaitingRoom(id='wr', code='WR', name='Waiting', floor='1', display_label='Waiting'))
        db.add(RoleDefinition(name='custom_tech', display_name='Technician', access_profile='radiographer', permissions=[]))
        db.flush()
        db.add(Doctor(id='room', name='Room 110', room_number='110', department='Radiology', designation='Room', waiting_room_id='wr', token_prefix='R110'))
        db.flush()
        db.add(Doctor(id='room-104', name='Room 104', room_number='104', department='Radiology', designation='Room', waiting_room_id='wr', token_prefix='R104'))
        db.flush()
        for user_id, role, room in [('alice', 'radiographer', 'room'), ('bob', 'custom_tech', 'room-104')]:
            db.add(User(id=user_id, username=user_id, full_name=user_id, role=role, doctor_id=room, password_hash='preserved'))
        db.add(User(id='admin', username='admin', full_name='Admin', role='admin', password_hash='preserved'))
        db.commit()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
    with Session(engine) as db:
        assert db.get(User, 'alice').username == '110'
        assert db.get(User, 'bob').username == '104'
        assert db.get(User, 'admin').username == 'admin'
        assert all(user.password_hash == 'preserved' for user in db.scalars(select(User)))
        assert db.get(User, 'bob').role == 'custom_tech'
        assert db.get(User, 'alice').doctor_id == 'room'
    engine.dispose()


def test_migration_stops_before_changes_when_room_has_duplicate_accounts():
    import pytest
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20260928_0032_room_user_ids.py'
    spec = importlib.util.spec_from_file_location('room_user_conflict_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with SessionLocal() as db:
        for username in ('first-tech', 'second-tech'):
            db.add(User(username=username, full_name=username, role='radiographer', doctor_id='dr-khan', password_hash='preserved'))
        db.commit()
        before = set(db.scalars(select(User.username)))
        with Operations.context(MigrationContext.configure(db.connection())):
            with pytest.raises(RuntimeError, match='multiple accounts'):
                migration.upgrade()
        assert set(db.scalars(select(User.username))) == before
