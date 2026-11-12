from app.database import SessionLocal
from app.models import User, RoleDefinition
from app.auth import hash_password, LEGACY_ROLE_PERMISSIONS
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_radiographer_registers_and_records_film_contrast_for_own_room():
    own = client.post('/api/v1/tokens', json=token_payload()).json()
    with SessionLocal() as db:
        db.add(RoleDefinition(name='radiographer', display_name='Radiographer', access_profile='radiographer', permissions=sorted(LEGACY_ROLE_PERMISSIONS['radiographer'])))
        db.add(User(username='205', full_name='Room 205', role='radiographer', doctor_id='dr-khan', password_hash=hash_password('RoomPass123!')))
        db.commit()
    client.cookies.clear()
    login = client.post('/api/v1/auth/login', json={'username':'205', 'password':'RoomPass123!'})
    assert login.status_code == 200
    assert 'queue.serial.create' in login.json()['permissions']
    created = client.post('/api/v1/tokens', json=token_payload('Room registered patient'))
    assert created.status_code == 201, created.text
    client.post(f"/api/v1/doctors/dr-khan/tokens/{own['id']}/call").raise_for_status()
    url = f"/api/v1/tokens/{own['id']}/supplies"
    saved = client.patch(url, json={'film': 3, 'contrast': 1})
    assert saved.status_code == 200, saved.text
    assert saved.json()['film'] == 3 and saved.json()['contrast'] == 1
    assert client.patch(url, json={'film':-1}).status_code == 422
    assert client.patch(url, json={'contrast':1.5}).status_code == 422
    assert client.patch(url, json={'patient_name':'Tampered'}).status_code == 422
    assert client.patch(url, json={'film':0}).json()['contrast'] == 1
    with SessionLocal() as db:
        user = db.query(User).filter_by(username='205').one()
        user.doctor_id = None
        db.commit()
    assert client.patch(url, json={'film':4}).status_code == 403
    with SessionLocal() as db:
        user = db.query(User).filter_by(username='205').one()
        user.doctor_id = 'dr-khan'
        db.commit()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{own['id']}/action", json={'action': 'start'}).raise_for_status()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{own['id']}/action", json={'action': 'complete'}).raise_for_status()
    completed_edit = client.patch(url, json={'film': 5, 'contrast': 2})
    assert completed_edit.status_code == 200, completed_edit.text
    assert completed_edit.json()['film'] == 5 and completed_edit.json()['contrast'] == 2
    assert completed_edit.json()['status'] == 'completed'
    assert completed_edit.json()['serial_number'] == own['serial_number']
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'AdminPass123!'}).raise_for_status()
    admin_edit = client.patch(url, json={'film': 5, 'contrast': 2})
    assert admin_edit.status_code == 200
    assert admin_edit.json()['film'] == 5 and admin_edit.json()['contrast'] == 2


def test_completed_entry_counts_are_updated_in_filtered_reception_report_and_audited():
    from datetime import date
    from sqlalchemy import select
    from app.models import AuditEvent
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{entry['id']}/action", json={'action': 'complete_without_call'}).raise_for_status()
    client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={}).raise_for_status()
    updated = client.patch(f"/api/v1/tokens/{entry['id']}/supplies", json={'film': 4, 'contrast': 2})
    assert updated.status_code == 200, updated.text
    assert updated.json()['status'] == 'completed'
    assert updated.json()['serial_number'] == entry['serial_number']
    assert updated.json()['report_verified'] is True
    rows = client.get('/api/v1/reports/reception', params={'date_from': str(date.today()), 'date_to': str(date.today()), 'status': 'completed', 'contrast': 'used'}).json()
    assert len(rows) == 1 and rows[0]['film'] == 4 and rows[0]['contrast'] == 2
    with SessionLocal() as db:
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'token.supplies_updated', AuditEvent.token_id == entry['id']))
        assert audit.actor == 'admin'
        assert audit.detail['changes'] == {'film': 4, 'contrast': 2}
