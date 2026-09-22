import asyncio

import pytest

from app.realtime import ChangeHub, mutation_topics


@pytest.mark.parametrize(('method', 'path', 'status', 'topics'), [
    ('POST', '/api/v1/tokens', 201, ['queue']),
    ('PATCH', '/api/v1/tokens/patient/classification', 200, ['queue']),
    ('POST', '/api/v1/doctors/doctor/claim/patient', 200, ['queue']),
    ('POST', '/api/v1/doctors/doctor/tokens/patient/action', 200, ['queue']),
    ('PATCH', '/api/v1/admin/doctors/doctor', 200, ['directory', 'queue']),
    ('POST', '/api/v1/appointments/visit/check-in', 200, ['queue']),
    ('PATCH', '/api/v1/lookups/item', 200, ['lookups', 'queue']),
    ('PUT', '/api/v1/settings/display', 200, ['queue']),
    ('GET', '/api/v1/tokens', 200, []),
    ('POST', '/api/v1/tokens', 403, []),
    ('POST', '/api/v1/bengali-name-suggestion', 200, []),
    ('POST', '/api/v1/settings/announcement/test', 202, []),
    ('POST', '/api/v1/devices/display/heartbeat', 200, []),
])
def test_only_successful_relevant_writes_invalidate_live_data(method, path, status, topics):
    assert mutation_topics(method, path, status) == topics


def test_change_notifications_are_patient_free_and_failed_clients_are_removed():
    class Socket:
        def __init__(self):
            self.messages = []
            self.fail = False
            self.closed = False
        async def accept(self):
            pass
        async def send_json(self, data):
            if self.fail:
                raise RuntimeError('Disconnected')
            self.messages.append(data)
        async def close(self, code):
            self.closed = True

    async def run():
        hub = ChangeHub()
        good, bad = Socket(), Socket()
        await hub.connect('application', good)
        await hub.connect('application', bad)
        bad.fail = True
        await hub.publish(['queue'])
        assert hub.connection_count('application') == 1
        assert bad.closed
        event = good.messages[-1]
        assert event['type'] == 'data.changed' and event['topics'] == ['queue']
        assert set(event) == {'event_id', 'sequence', 'type', 'reason', 'waiting_room', 'occurred_at', 'topics'}

    asyncio.run(run())
