from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditEvent, QueueToken, RoleDefinition, User
from app.auth import hash_password
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_separate_body_parts_have_unique_serials_and_independent_verification():
    first_payload = token_payload()
    first_payload['mri_area'] = 'Brain'
    second_payload = {**first_payload, 'mri_area': 'Spine'}
    first = client.post('/api/v1/tokens', json=first_payload)
    second = client.post('/api/v1/tokens', json=second_payload)
    assert first.status_code == second.status_code == 201
    first, second = first.json(), second.json()
    assert first['serial_number'] != second['serial_number']
    assert second['sequence'] == first['sequence'] + 1
    url = f"/api/v1/tokens/{first['id']}/report-verification"
    verified = client.patch(url, json={})
    assert verified.status_code == 200, verified.text
    assert verified.json()['report_verified'] is True
    assert verified.json()['report_verified_by'] == 'admin'
    assert verified.json()['report_verified_at']
    # Repeated clicks must not rewrite who verified it or generate duplicate audits.
    client.patch(url, json={}).raise_for_status()
    with SessionLocal() as db:
        token = db.get(QueueToken, first['id'])
        assert token.report_verified_by == 'admin'
        assert db.get(QueueToken, second['id']).report_verified is False
        assert len(list(db.scalars(select(AuditEvent).where(AuditEvent.action == 'token.report_verified')))) == 1
    counts = client.get('/api/v1/reports/verification-summary').json()
    assert counts == {'total': 2, 'verified': 1, 'pending': 1}
    report = client.get('/api/v1/reports/reception', params={'report_verified': 'true'})
    assert [row['id'] for row in report.json()] == [first['id']]
    summary = client.get('/api/v1/reports/mri-summary', params={'date_from': str(date.today()), 'date_to': str(date.today())}).json()
    assert summary['verified'] == summary['pending'] == 1
    for endpoint in ('/api/v1/reports/reception.xlsx', '/api/v1/reports/reception.pdf', '/api/v1/reports/mri-summary.xlsx', '/api/v1/reports/mri-summary.pdf'):
        response = client.get(endpoint, params={'date_from': str(date.today()), 'date_to': str(date.today())})
        assert response.status_code == 200, response.text[:200]


def test_verification_requires_permission():
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    with SessionLocal() as db:
        db.add(RoleDefinition(name='viewer', display_name='Viewer', access_profile='auditor', permissions=['queue.view']))
        db.add(User(username='viewer', full_name='Viewer', role='viewer', password_hash=hash_password('ViewerPass123!')))
        db.commit()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'viewer', 'password': 'ViewerPass123!'}).raise_for_status()
    response = client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={})
    assert response.status_code == 403


def test_role_permission_is_configurable_and_radiographer_room_is_enforced():
    from app.auth import LEGACY_ROLE_PERMISSIONS
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    # Custom roles can receive or lose the new permission through Settings APIs.
    created = client.post('/api/v1/roles', json={'name': 'report_clerk', 'display_name': 'Report clerk',
        'access_profile': 'auditor', 'permissions': ['reports.verify', 'reports.view']})
    assert created.status_code in (200, 201), created.text
    assert 'reports.verify' in created.json()['permissions']
    with SessionLocal() as db:
        db.add(User(username='clerk', full_name='Clerk', role='report_clerk', password_hash=hash_password('ClerkPass123!')))
        db.add(RoleDefinition(name='radiographer', display_name='Radiographer', access_profile='radiographer', permissions=sorted(LEGACY_ROLE_PERMISSIONS['radiographer'])))
        db.add(User(username='rad', full_name='Rad', role='radiographer', doctor_id='dr-khan', password_hash=hash_password('RadioPass123!')))
        db.commit()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'clerk', 'password': 'ClerkPass123!'}).raise_for_status()
    client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={}).raise_for_status()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'AdminPass123!'}).raise_for_status()
    client.patch('/api/v1/roles/report_clerk', json={'permissions': ['reports.view']}).raise_for_status()
    other = client.post('/api/v1/tokens', json={**token_payload(), 'doctor_id': None}).json()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'clerk', 'password': 'ClerkPass123!'}).raise_for_status()
    assert client.patch(f"/api/v1/tokens/{other['id']}/report-verification", json={}).status_code == 403
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'rad', 'password': 'RadioPass123!'}).raise_for_status()
    assert client.patch(f"/api/v1/tokens/{other['id']}/report-verification", json={}).status_code == 403
    assert client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={}).status_code == 200


def test_database_rejects_duplicate_serial_and_clinical_edit_clears_verification():
    import pytest
    from sqlalchemy.exc import IntegrityError
    entry = client.post('/api/v1/tokens', json=token_payload()).json()
    with SessionLocal() as db:
        original = db.get(QueueToken, entry['id'])
        values = {column.name: getattr(original, column.name) for column in QueueToken.__table__.columns if column.name != 'id'}
        values['sequence'] += 100
        db.add(QueueToken(**values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    client.patch(f"/api/v1/tokens/{entry['id']}/report-verification", json={}).raise_for_status()
    edited = client.patch(f"/api/v1/tokens/{entry['id']}", json={**token_payload(), 'mri_area': 'Spine'})
    assert edited.status_code == 200, edited.text
    assert edited.json()['serial_number'] == entry['serial_number']
    assert edited.json()['report_verified'] is False
