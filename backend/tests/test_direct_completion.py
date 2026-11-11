import pytest
from datetime import datetime
from sqlalchemy import select
from app.database import SessionLocal
from app.models import AuditEvent, CallEvent, Doctor, QueueToken
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_waiting_entry_completes_without_call_or_start_and_preserves_serial():
    entry = client.post('/api/v1/tokens', json={**token_payload(), 'doctor_id': None, 'room_number': ''}).json()
    url = f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action"
    response = client.post(url, json={'action': 'complete_without_call'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'completed'
    assert result['serial_number'] == entry['serial_number']
    assert result['doctor_id'] == 'dr-khan'
    assert result['completed_at'] and result['called_at'] is None and result['started_at'] is None
    assert client.post(url, json={'action': 'complete_without_call'}).status_code == 409
    with SessionLocal() as db:
        assert list(db.scalars(select(CallEvent))) == []
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'queue.complete_without_call'))
        assert audit.previous_status == 'waiting' and audit.new_status == 'completed'


def test_direct_completion_cannot_take_another_rooms_entry_or_bypass_normal_complete():
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    with SessionLocal() as db:
        db.add(Doctor(id='other', name='Other', department='MRI', designation='Radiographer', room_number='999', waiting_room_id='waiting-room-1', token_prefix='OT'))
        db.commit()
    assert client.post(f"/api/v1/doctors/other/tokens/{entry['id']}/action", json={'action': 'complete_without_call'}).status_code in (403, 409)
    url = f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action"
    assert client.post(url, json={'action': 'complete'}).status_code == 409
    assert client.post(url, json={'action': 'complete_without_call'}).status_code == 200


@pytest.mark.parametrize('status', ['called', 'recalled'])
def test_called_entry_can_complete_directly_without_rewriting_call_history(status):
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    called_at = datetime(2026, 11, 11, 8, 0)
    with SessionLocal() as db:
        token = db.get(QueueToken, entry['id'])
        token.status = status
        token.called_at = called_at
        db.commit()
    url = f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action"
    response = client.post(url, json={'action': 'complete_without_call'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'completed'
    assert result['serial_number'] == entry['serial_number']
    assert result['called_at'] == called_at.isoformat()
    assert result['started_at'] is None and result['completed_at']
    with SessionLocal() as db:
        assert list(db.scalars(select(CallEvent))) == []
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'queue.complete_without_call'))
        assert audit.previous_status == status and audit.new_status == 'completed'


def test_radiographer_can_complete_assigned_and_unassigned_entries_directly():
    from app.auth import hash_password, LEGACY_ROLE_PERMISSIONS
    from app.models import RoleDefinition, User
    own = client.post('/api/v1/tokens', json=token_payload()).json()
    unassigned = client.post('/api/v1/tokens', json={**token_payload(), 'doctor_id': None}).json()
    with SessionLocal() as db:
        db.add(RoleDefinition(name='radiographer', display_name='Radiographer', access_profile='radiographer', permissions=sorted(LEGACY_ROLE_PERMISSIONS['radiographer'])))
        db.add(User(username='rad', full_name='Radiographer', role='radiographer', doctor_id='dr-khan', password_hash=hash_password('RadioPass123!')))
        db.commit()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'rad', 'password': 'RadioPass123!'}).raise_for_status()
    for entry in (own, unassigned):
        response = client.post(f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action", json={'action': 'complete_without_call'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'completed'
        assert response.json()['serial_number'] == entry['serial_number']
