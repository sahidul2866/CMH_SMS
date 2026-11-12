from datetime import date, timedelta
from io import BytesIO
from openpyxl import load_workbook
from app.database import SessionLocal
from app.models import QueueToken
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_reception_service_search_is_partial_case_insensitive_and_keeps_filters_and_exports():
    first = client.post('/api/v1/tokens', json={**token_payload('First entry'), 'service_number': 'BA-12345'}).json()
    client.post('/api/v1/tokens', json={**token_payload('Second entry'), 'service_number': 'ba-12399', 'contrast': 1}).raise_for_status()
    old = client.post('/api/v1/tokens', json={**token_payload('Old entry'), 'service_number': 'BA-12388'}).json()
    with SessionLocal() as db:
        db.get(QueueToken, old['id']).token_date = date.today() - timedelta(days=1)
        db.commit()
    search = {'service_number': '  bA-123  '}
    rows = client.get('/api/v1/reports/reception', params=search).json()
    assert {row['patient_name'] for row in rows} == {'First entry', 'Second entry'}
    filtered = client.get('/api/v1/reports/reception', params={**search, 'contrast': 'used'}).json()
    assert [row['patient_name'] for row in filtered] == ['Second entry']
    empty = client.get('/api/v1/reports/reception', params={'service_number': 'no-match'}).json()
    assert empty == []
    workbook_response = client.get('/api/v1/reports/reception.xlsx', params={**search, 'contrast': 'used'})
    assert workbook_response.status_code == 200
    sheet = load_workbook(BytesIO(workbook_response.content)).active
    assert sheet.max_row == 2 and sheet['E2'].value == 'Second entry'
    assert client.get('/api/v1/reports/reception.pdf', params=search).status_code == 200


def test_service_search_treats_wildcards_as_literal_characters():
    for value in ('BA%100', 'BA_100', 'BAX100'):
        client.post('/api/v1/tokens', json={**token_payload(), 'service_number': value}).raise_for_status()
    for value in ('%', '_'):
        rows = client.get('/api/v1/reports/reception', params={'service_number': value}).json()
        assert len(rows) == 1 and value in rows[0]['service_number']
    assert len(client.get('/api/v1/reports/reception', params={'service_number': ' '}).json()) == 3
