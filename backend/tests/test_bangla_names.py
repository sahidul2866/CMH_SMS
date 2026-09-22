from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bangla_names import suggest_bengali_name, validate_bengali_name
from app.announcement import Announcement, AnnouncementEngine


@pytest.mark.parametrize(('original', 'expected'), [
    ('Md. Rahim Uddin', 'মোহাম্মদ রহিম উদ্দিন'),
    ('MD. RAHIM UDDIN', 'মোহাম্মদ রহিম উদ্দিন'),
    ('Nusrat Jahan', 'নুসরাত জাহান'),
    ('মোহাম্মদ Rahim উদ্দিন', 'মোহাম্মদ রহিম উদ্দিন'),
    ('A. B. Karim', 'এ বি করিম'),
    ('Mahir', 'মাহির'),
])
def test_offline_name_suggestions(original, expected):
    assert suggest_bengali_name(original) == expected
    assert validate_bengali_name(expected) == expected


@pytest.mark.parametrize('name', ['Rahim', 'রহিম Uddin', '123', '   .   ', 'রহিম <script>'])
def test_bengali_pronunciation_rejects_unsupported_script(name):
    with pytest.raises(ValueError):
        validate_bengali_name(name)


def test_blank_pronunciation_is_optional():
    assert validate_bengali_name('   ') is None
    assert validate_bengali_name(None) is None


@pytest.mark.parametrize('service_number', [None, '', 'BA-102'])
@pytest.mark.parametrize('saved_name', [None, 'রাহীম উদ্দীন'])
def test_offline_announcement_uses_one_bengali_voice_with_or_without_service_number(monkeypatch, tmp_path, service_number, saved_name):
    engine = AnnouncementEngine()
    engine.cache_dir = tmp_path
    calls = []
    monkeypatch.setattr(engine, '_synthesise_offline_bengali', lambda text, rate: calls.append(text) or tmp_path / 'bengali.wav')
    monkeypatch.setattr(engine, '_synthesise', lambda *args, **kwargs: pytest.fail('Must not switch to English or splice voices'))
    item = Announcement(token_number='00001/26', patient_name='Rahim Uddin', patient_name_bn=saved_name,
                        service_number=service_number, doctor_name='Dr. Khan', room_number='205',
                        language='bn', voice_mode='offline_neural')
    assert engine._prepare(item) == [tmp_path / 'bengali.wav']
    assert len(calls) == 1
    assert f"রোগী {saved_name or 'রহিম উদ্দিন'}" in calls[0]
    assert 'কক্ষ নম্বর দুই শূন্য পাঁচ' in calls[0]
    assert ('সার্ভিস নম্বর' in calls[0]) == bool(service_number)
    assert not any(char.isascii() and char.isalpha() for char in calls[0])


def test_english_announcement_keeps_original_name(monkeypatch, tmp_path):
    engine = AnnouncementEngine()
    engine.cache_dir = tmp_path
    calls = []
    monkeypatch.setattr(engine, '_synthesise', lambda text, voice, rate: calls.append((text, voice)) or tmp_path / 'english.wav')
    item = Announcement(token_number='00001/26', patient_name='Rahim Uddin', patient_name_bn='রাহীম উদ্দীন',
                        service_number=None, doctor_name='Dr. Khan', room_number='205', language='en')
    engine._prepare(item)
    assert calls == [('Rahim Uddin, please proceed to Dr. Khan, room 205.', 'en_male')]


def test_queued_announcement_keeps_saved_bengali_spelling(monkeypatch):
    monkeypatch.setenv('CMH_SMS_AUDIO_ENABLED', 'true')
    engine = AnnouncementEngine()
    token = SimpleNamespace(token_number='00001/26', patient_name='Rahim', patient_name_bn='রহিম', room_number='205')
    assert engine.enqueue(token, {'language': 'bn'})
    assert engine._queue.get_nowait().patient_name_bn == 'রহিম'


def test_unsupported_name_script_uses_spoken_token_in_same_voice(monkeypatch, tmp_path):
    engine = AnnouncementEngine()
    engine.cache_dir = tmp_path
    calls = []
    monkeypatch.setattr(engine, '_synthesise_offline_bengali', lambda text, rate: calls.append(text) or tmp_path / 'bengali.wav')
    item = Announcement(token_number='001', patient_name='王明', service_number=None, doctor_name='Doctor',
                        room_number='205', language='bn', voice_mode='offline_neural')
    engine._prepare(item)
    assert 'টোকেন নম্বর শূন্য শূন্য এক' in calls[0]


@pytest.mark.parametrize(('settings', 'language'), [
    ({'enabled': True, 'language_order': ['bn']}, 'bn'),
    ({'enabled': True, 'language_order': ['en']}, 'en'),
    ({'enabled': True, 'language_order': ['bn', 'en']}, 'both'),
    ({'language_order': ['bn', 'en']}, 'both'),
])
def test_announcement_language_choices(settings, language):
    engine = AnnouncementEngine()
    engine.enabled = True
    token = SimpleNamespace(token_number='001', patient_name='Rahim', room_number='205')
    assert engine.enqueue(token, settings)
    assert engine._queue.get_nowait().language == language


def test_off_blocks_new_announcements_and_discards_queued_audio():
    engine = AnnouncementEngine()
    engine.enabled = True
    token = SimpleNamespace(token_number='001', patient_name='Rahim', room_number='205')
    assert not engine.enqueue(token, {'enabled': False, 'language_order': ['bn', 'en']})
    assert engine._queue.empty()
    assert engine.enqueue(token, {'language_order': ['bn']})
    engine.set_announcements_enabled(False)
    assert engine._queue.empty()
    assert not engine.enqueue(token, {'enabled': True})
    engine.set_announcements_enabled(True)
    assert engine.enqueue(token, {'enabled': True, 'language_order': ['en']})


def test_muting_during_playback_does_not_resume_old_announcement(monkeypatch, tmp_path):
    import asyncio
    engine = AnnouncementEngine()
    engine.enabled = True
    played = []
    monkeypatch.setattr(engine, '_prepare', lambda item: [tmp_path / 'bn.wav', tmp_path / 'en.wav'])

    def play(path):
        played.append(path.name)
        engine.set_announcements_enabled(False)
        engine.set_announcements_enabled(True)

    async def inline(function, *args):
        return function(*args)

    monkeypatch.setattr(engine, '_play', play)
    monkeypatch.setattr('app.announcement.asyncio.to_thread', inline)

    async def run():
        task = asyncio.create_task(engine._run())
        engine.enqueue(SimpleNamespace(token_number='001', patient_name='Rahim', room_number='205'), {'repeat_count': 3, 'language_order': ['bn', 'en']})
        await asyncio.wait_for(engine._queue.join(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert played == ['bn.wav']
