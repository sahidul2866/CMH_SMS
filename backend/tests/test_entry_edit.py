from datetime import date
from sqlalchemy import select
from app.database import SessionLocal
from app.models import AuditEvent, QueueToken, RegistrationCounter, RoleDefinition, User
from app.auth import hash_password, LEGACY_ROLE_PERMISSIONS
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_full_completed_entry_edit_preserves_identity_status_and_history():
    payload = token_payload()
    entry = client.post('/api/v1/tokens', json=payload).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action", json={'action': 'complete_without_call'}).raise_for_status()
    verified = client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={}).json()
    with SessionLocal() as db:
        counter = db.get(RegistrationCounter, date.today().year).sequence
    changes = {**payload, 'patient_name': 'Corrected Patient', 'age': 54, 'unit': 'Updated unit',
               'mri_area': 'Spine', 'film': 3, 'contrast': 1, 'report': 'Corrected report',
               'status': 'waiting', 'serial_number': '99999/26', 'doctor_id': 'not-a-room',
               'room_number': '999', 'token_date': '2001-01-01'}
    response = client.patch(f"/api/v1/tokens/{entry['id']}", json=changes)
    assert response.status_code == 200, response.text
    updated = response.json()
    for key in ('patient_name', 'age', 'unit', 'mri_area', 'film', 'contrast', 'report'):
        assert updated[key] == changes[key]
    for key in ('id', 'serial_number', 'token_number', 'created_at', 'token_date', 'doctor_id', 'room_number', 'status', 'completed_at'):
        assert updated[key] == verified[key]
    assert not updated['report_verified']
    with SessionLocal() as db:
        assert db.get(RegistrationCounter, date.today().year).sequence == counter
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'token.edited'))
        assert audit.detail['before']['patient_name'] == entry['patient_name']
        assert audit.detail['after']['patient_name'] == 'Corrected Patient'
    rows = client.get('/api/v1/reports/reception', params={'status': 'completed'}).json()
    assert rows[0]['patient_name'] == 'Corrected Patient'


def test_radiographer_can_edit_completed_own_entry_but_not_other_room():
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    with SessionLocal() as db:
        db.get(QueueToken, entry['id']).status = 'completed'
        db.add(RoleDefinition(name='radiographer', display_name='Radiographer', access_profile='radiographer', permissions=sorted(LEGACY_ROLE_PERMISSIONS['radiographer'])))
        db.add(User(username='rad', full_name='Rad', role='radiographer', doctor_id='dr-khan', password_hash=hash_password('RadioPass123!')))
        db.commit()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'rad', 'password': 'RadioPass123!'}).raise_for_status()
    response = client.patch(f"/api/v1/tokens/{entry['id']}", json={**token_payload(), 'film': 7, 'report': 'Updated'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed'
    with SessionLocal() as db:
        db.scalar(select(User).where(User.username == 'rad')).doctor_id = None
        db.commit()
    assert client.patch(f"/api/v1/tokens/{entry['id']}", json=token_payload()).status_code == 403
