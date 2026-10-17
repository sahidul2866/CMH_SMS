import asyncio
import time
from types import SimpleNamespace

import pytest

from app.announcement import AnnouncementEngine


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



def test_calls_and_recalls_always_play_on_server_even_with_old_browser_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv('CMH_SMS_AUDIO_OUTPUT', 'browser')
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.cache_dir = tmp_path
    clips = [tmp_path / 'bangla.wav', tmp_path / 'english.wav']
    played = []
    monkeypatch.setattr(engine, '_prepare', lambda item: clips)
    monkeypatch.setattr(engine, '_play', played.append)

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
    assert engine.output == 'server'
    assert played == clips * 4
    assert engine.completed_count == 2
    assert engine.last_error is None


def test_pending_server_diagnostic_reports_timeout_and_cancelled_queue():
    engine = AnnouncementEngine()
    engine.enabled = True
    engine.diagnostics['test'] = {'phase': 'server_playing', 'detail': 'Waiting for player.', 'started': time.monotonic() - 121}
    assert 'Timed out during server_playing' in engine.diagnostic_status('test')['detail']
    engine.diagnostics['test']['phase'] = 'queued'
    engine.enqueue(SimpleNamespace(token_number='001', patient_name='Patient', room_number='205'), diagnostic_id='test')
    engine.set_announcements_enabled(False)
    assert engine.diagnostic_status('test')['phase'] == 'cancelled'
