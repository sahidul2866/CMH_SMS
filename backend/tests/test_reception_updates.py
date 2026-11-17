from datetime import date, timedelta

from app.auth import hash_password
from app.database import SessionLocal
from app.models import QueueToken, RoleDefinition, User
from test_queue import client, setup_function, token_payload  # noqa: F401


def login_reception():
    with SessionLocal() as db:
        db.add(RoleDefinition(name='desk', display_name='Desk', access_profile='reception',
                              permissions=['pages.reception', 'queue.serial.create', 'master_data.view']))
        db.add(User(username='desk', full_name='Desk', role='desk', password_hash=hash_password('ReceptionPass123!')))
        db.commit()
    client.cookies.clear()
    client.post('/api/v1/auth/login', json={'username': 'desk', 'password': 'ReceptionPass123!'}).raise_for_status()


def test_reception_search_includes_historical_patients_and_escapes_wildcards():
    entry = client.post('/api/v1/tokens', json=token_payload('Historical Patient')).json()
    with SessionLocal() as db:
        token = db.get(QueueToken, entry['id'])
        token.token_date = date.today() - timedelta(days=730)
        token.status = 'completed'
        db.commit()
    login_reception()
    for query in ['historical', 'BA-TEST', entry['serial_number']]:
        result = client.get('/api/v1/registration/patient-search', params={'q': query})
        assert result.status_code == 200
        assert [row['id'] for row in result.json()] == [entry['id']]
    assert client.get('/api/v1/registration/patient-search', params={'q': '%'}).json() == []
    client.cookies.clear()
    assert client.get('/api/v1/registration/patient-search', params={'q': 'Patient'}).status_code == 401


def test_reception_can_mark_every_patient_status_reported_once():
    entries = []
    for status in ['waiting', 'called', 'recalled', 'in_progress', 'completed', 'skipped', 'cancelled', 'no_show']:
        response = client.post('/api/v1/tokens', json=token_payload(status))
        response.raise_for_status()
        entry = response.json()
        with SessionLocal() as db:
            db.get(QueueToken, entry['id']).status = status
            db.commit()
        entries.append(entry)
    login_reception()
    for entry in entries:
        endpoint = f"/api/v1/tokens/{entry['id']}/report-verification"
        marked = client.patch(endpoint)
        assert marked.status_code == 200
        assert marked.json()['report_verified'] is True
        assert marked.json()['report_verified_by'] == 'desk'
        assert client.patch(endpoint).json()['report_verified_at'] == marked.json()['report_verified_at']


def test_reception_generates_unique_ids_and_dropdowns_are_manageable():
    for category, label in [('mri_area', 'Brain'), ('ward_text', 'Ward 7'), ('unit', 'Example unit')]:
        response = client.post('/api/v1/lookups', json={'category': category, 'value': 'example', 'label': label})
        assert response.status_code == 201
        updated = client.patch(f"/api/v1/lookups/{response.json()['id']}", json={'label': label + ' updated'})
        assert updated.status_code == 200
    login_reception()
    preview = client.get('/api/v1/registration-preview')
    assert preview.status_code == 200
    first = client.post('/api/v1/tokens', json=token_payload()).json()
    second = client.post('/api/v1/tokens', json={**token_payload(), 'mri_area': 'Custom MRI part', 'unit': 'Custom unit'}).json()
    assert first['serial_number'] == preview.json()['serial_number']
    assert second['serial_number'] != first['serial_number']
    assert second['mri_area'] == 'Custom MRI part'
    options = client.get('/api/v1/lookups').json()
    assert {row['category'] for row in options} >= {'mri_area', 'ward_text', 'unit'}
