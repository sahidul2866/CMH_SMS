from datetime import date, timedelta

from app.database import SessionLocal
from app.models import QueueToken
from test_queue import client, setup_function, token_payload  # noqa: F401


def test_shared_dashboard_filters_cover_cards_rooms_and_drilldowns():
    today = date.today()
    yesterday = today - timedelta(days=1)
    rows = [client.post('/api/v1/tokens', json=token_payload(name)).json()
            for name in ('Today verified', 'Today pending', 'Yesterday pending')]
    client.patch(f"/api/v1/tokens/{rows[0]['id']}/report-verification", json={}).raise_for_status()
    with SessionLocal() as db:
        db.get(QueueToken, rows[1]['id']).priority = 'vip'
        old = db.get(QueueToken, rows[2]['id'])
        old.token_date = yesterday
        old.status = 'completed'
        db.commit()
    cases = [({}, 2, 1),
             ({'date_from': str(yesterday), 'date_to': str(yesterday)}, 1, 0),
             ({'date_from': str(yesterday), 'date_to': str(today)}, 3, 1),
             ({'priority': 'vip'}, 1, 0),
             ({'priority': 'non_vip'}, 1, 1),
             ({'report_verified': 'true'}, 1, 1),
             ({'report_verified': 'false'}, 1, 0),
             ({'doctor_id': 'missing-room'}, 0, 0)]
    for filters, total, verified in cases:
        response = client.get('/api/v1/dashboard', params=filters)
        assert response.status_code == 200, response.text
        dashboard = response.json()
        assert dashboard['total'] == total
        assert dashboard['report_verified'] == verified
        assert dashboard['report_pending'] == total - verified
        patients = client.get('/api/v1/dashboard/patients', params=filters).json()
        assert len(patients) == total
        for status, expected in [('verified', verified), ('unverified', total - verified)]:
            detail = client.get('/api/v1/dashboard/patients', params={**filters, 'status': status})
            assert detail.status_code == 200, detail.text
            assert len(detail.json()) == expected
        if total:
            assert sum(room['total'] for room in dashboard['rooms']) == total
    invalid = {'date_from': str(today), 'date_to': str(yesterday)}
    assert client.get('/api/v1/dashboard', params=invalid).status_code == 422
    assert client.get('/api/v1/dashboard/patients', params=invalid).status_code == 422
