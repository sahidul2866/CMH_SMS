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

    async def broadcast(*args, **payload):
        events.append(payload)

    monkeypatch.setattr(engine, '_prepare', lambda item: [clip])
    monkeypatch.setattr(browser_audio_hub, 'broadcast', broadcast)
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
