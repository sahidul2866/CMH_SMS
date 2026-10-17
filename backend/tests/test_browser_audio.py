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


@pytest.mark.parametrize('failure_stage', ['generating', 'server_playing', None])
def test_diagnostic_reports_its_own_generation_or_player_failure(monkeypatch, tmp_path, failure_stage):
    import time
    import subprocess
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.output = 'server'
    engine.cache_dir = tmp_path
    engine.diagnostics['test'] = {'test_id': 'test', 'phase': 'queued', 'detail': '', 'started': time.monotonic()}
    clip = tmp_path / 'test.wav'
    clip.write_bytes(b'voice')

    def prepare(item):
        if failure_stage == 'generating':
            raise RuntimeError('Neural model file is missing')
        return [clip]

    def play(path):
        if failure_stage == 'server_playing':
            raise subprocess.CalledProcessError(1, ['player'], stderr='No default output device')

    monkeypatch.setattr(engine, '_prepare', prepare)
    monkeypatch.setattr(engine, '_play', play)

    async def scenario():
        await engine.start()
        try:
            engine.enqueue(SimpleNamespace(token_number='001', patient_name='Patient', room_number='205'),
                           diagnostic_id='test')
            await asyncio.wait_for(engine._queue.join(), timeout=2)
        finally:
            await engine.stop()

    asyncio.run(scenario())
    result = engine.diagnostic_status('test')
    assert result['phase'] == ('failed' if failure_stage else 'completed')
    if failure_stage:
        assert failure_stage in result['detail']
        assert ('Neural model file is missing' if failure_stage == 'generating' else 'No default output device') in result['detail']


def test_browser_diagnostic_requires_playback_confirmation_and_times_out(monkeypatch):
    import time
    engine = AnnouncementEngine()
    engine.diagnostics['test'] = {'phase': 'browser_pending', 'detail': 'Waiting for playback.', 'started': time.monotonic()}
    engine.browser_report('unknown', 'completed')
    assert engine.diagnostic_status('test')['phase'] == 'browser_pending'
    engine.browser_report('test', 'failed', 'EncodingError: Unsupported audio format')
    result = engine.diagnostic_status('test')
    assert result['phase'] == 'failed'
    assert 'EncodingError: Unsupported audio format' in result['detail']
    engine.browser_report('test', 'completed')
    assert engine.diagnostic_status('test')['phase'] == 'failed'
    engine.diagnostics['test'].update(phase='browser_pending', started=time.monotonic() - 121)
    assert 'Timed out during browser_pending' in engine.diagnostic_status('test')['detail']


def test_browser_diagnostic_confirms_completion_and_queued_test_cancels():
    import time
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.diagnostics['test'] = {'phase': 'browser_pending', 'detail': '', 'started': time.monotonic()}
    engine.browser_report('test', 'playing')
    assert engine.diagnostic_status('test')['phase'] == 'browser_playing'
    engine.browser_report('test', 'completed')
    assert engine.diagnostic_status('test')['phase'] == 'completed'
    engine.diagnostics['test']['phase'] = 'queued'
    engine.enqueue(SimpleNamespace(token_number='001', patient_name='Patient', room_number='205'), diagnostic_id='test')
    engine.set_announcements_enabled(False)
    assert engine.diagnostic_status('test')['phase'] == 'cancelled'


def test_neural_fallback_warning_is_attached_to_the_current_test(monkeypatch, tmp_path):
    import time
    from app.announcement import Announcement, diagnostic_context
    engine = AnnouncementEngine()
    engine.diagnostics['test'] = {'phase': 'generating', 'detail': '', 'started': time.monotonic()}
    monkeypatch.setattr(engine, '_synthesise_offline_bengali', lambda *args: (_ for _ in ()).throw(RuntimeError('Model missing')))
    monkeypatch.setattr(engine, '_synthesise', lambda *args, **kwargs: tmp_path / 'basic.wav')
    context = diagnostic_context.set('test')
    try:
        engine._prepare(Announcement('001', 'Patient', None, 'Doctor', '205', language='bn', voice_mode='offline_neural'))
    finally:
        diagnostic_context.reset(context)
    assert 'Model missing' in engine.diagnostic_status('test')['warnings'][0]
    assert 'basic offline fallback' in engine.diagnostic_status('test')['warnings'][0]
