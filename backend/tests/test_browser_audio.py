import asyncio
import base64
from types import SimpleNamespace

from app.announcement import AnnouncementEngine
from app.realtime import browser_audio_hub


def test_repeated_patient_calls_are_delivered_without_server_playback(monkeypatch, tmp_path):
    monkeypatch.setenv('CMH_SMS_AUDIO_OUTPUT', 'browser')
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.cache_dir = tmp_path
    events = []
    clip = tmp_path / 'voice.wav'
    clip.write_bytes(b'neural voice')

    async def deliver(**payload):
        events.append(payload)
        return 1

    monkeypatch.setattr(engine, '_prepare', lambda item: [clip])
    monkeypatch.setattr(browser_audio_hub, 'deliver', deliver)
    monkeypatch.setattr(engine, '_play', lambda path: (_ for _ in ()).throw(AssertionError('Server playback')))

    async def scenario():
        await engine.start()
        try:
            for _ in range(2):  # Initial call followed by recall of the same patient.
                engine.enqueue(SimpleNamespace(token_number='001', patient_name='Patient', room_number='205'),
                               {'language': 'en', 'repeat_count': 2, 'volume': 0.5})
            await asyncio.wait_for(engine._queue.join(), timeout=2)
        finally:
            await engine.stop()

    asyncio.run(scenario())
    assert len(events) == 2
    assert all(base64.b64decode(event['clips'][0]) == b'neural voice' for event in events)
    assert all(event['repeat_count'] == 2 and event['volume'] == 0.5 for event in events)
    assert engine.delivered_count == 2
    assert engine.completed_count == 0
    assert engine.last_error is None


import pytest


@pytest.mark.parametrize('listeners', [0, 1])
def test_server_fallback_uses_identical_clips_only_without_browser_delivery(monkeypatch, tmp_path, listeners):
    monkeypatch.setenv('CMH_SMS_AUDIO_OUTPUT', 'browser')
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.cache_dir = tmp_path
    paths = [tmp_path / 'bangla.wav', tmp_path / 'english.wav']
    for path in paths:
        path.write_bytes(path.name.encode())
    played = []

    async def deliver(**payload):
        assert [base64.b64decode(clip) for clip in payload['clips']] == [p.read_bytes() for p in paths]
        return listeners

    monkeypatch.setattr(engine, '_prepare', lambda item: paths)
    monkeypatch.setattr(engine, '_play', played.append)
    monkeypatch.setattr(browser_audio_hub, 'deliver', deliver)

    async def scenario():
        await engine.start()
        try:
            for _ in range(2):
                engine.enqueue(SimpleNamespace(token_number='001', patient_name='Patient', room_number='205'),
                               {'repeat_count': 2})
            await asyncio.wait_for(engine._queue.join(), timeout=2)
        finally:
            await engine.stop()

    asyncio.run(scenario())
    assert played == (paths * 4 if listeners == 0 else [])
    assert engine.completed_count == (2 if listeners == 0 else 0)
    assert engine.last_error is None


def test_audio_hub_counts_deliveries_and_removes_failed_browsers():
    from app.realtime import BrowserAudioHub

    class Client:
        def __init__(self, fail=False):
            self.fail = fail
        async def send_json(self, event):
            if self.fail:
                raise ConnectionError('Browser closed')

    async def scenario():
        hub = BrowserAudioHub()
        assert await hub.deliver(clips=[]) == 0
        good, bad = Client(), Client(True)
        hub._connections['audio'].update([good, bad])
        assert await hub.deliver(clips=[]) == 1
        assert hub.connection_count('audio') == 1
        await hub.disconnect('audio', good)
        assert await hub.deliver(clips=[]) == 0
        hub._connections['audio'].add(Client(True))
        assert await hub.deliver(clips=[]) == 0
        assert hub.connection_count('audio') == 0

    asyncio.run(scenario())
