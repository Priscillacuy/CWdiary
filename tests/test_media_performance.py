import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from audio_service import AudioService, session_steps
from image_service import ImageService


def test_media_preparation_overlaps_independent_narrations(tmp_path, monkeypatch):
    service = AudioService(tmp_path)
    gate = threading.Barrier(3, timeout=3)
    def speech(text, voice, language):
        gate.wait()
        return 'cached-' + text
    monkeypatch.setattr(service, 'speech', speech)
    monkeypatch.setattr(service, 'music', lambda track: None)
    value = dict(steps=[dict(text='one'), dict(text='two')], closing_text='bye', voice='female', language='en', music='daylight')
    service._complete_media(value)
    assert [s['speech'] for s in value['steps']] == ['cached-one', 'cached-two']
    assert value['closing_speech'] == 'cached-bye'


def test_spoken_rewrite_cache_survives_voice_duration_and_restart(tmp_path, monkeypatch):
    plan = [dict(activity_id='rest', category='rest', title='休息', description='坐一会儿。', duration_minutes=5)]
    rewrite = Mock(side_effect=lambda steps, source, target: [{**s, 'title':'休息一下'} for s in steps])
    for minutes in (1, 3):
        service = AudioService(tmp_path)
        monkeypatch.setattr(service, '_translate_steps', rewrite)
        result = service.translated_steps(session_steps(plan, minutes, 'zh'), 'zh', 'zh')
        assert result[0]['duration_seconds'] == minutes * 60
        assert result[0]['title'] == '休息一下'
    assert rewrite.call_count == 1


def test_cloud_images_poll_once_without_sleep_or_waiting_for_completion(tmp_path, monkeypatch):
    from contextlib import nullcontext
    service = ImageService(tmp_path)
    service.key = 'test-only'
    service.file_store = Mock(load=lambda path, **kw: path, upload=lambda path: None, lease=lambda path: nullcontext(True))
    monkeypatch.setattr('image_service.time.sleep', lambda seconds: (_ for _ in ()).throw(AssertionError('Cloud polling must not sleep')))
    post = Mock(return_value=Mock(status_code=200, json=lambda: {'id':'job', 'status':'running'}))
    get = Mock(return_value=Mock(status_code=200, json=lambda: {'id':'job', 'status':'running'}))
    monkeypatch.setattr('image_service.requests.post', post)
    monkeypatch.setattr('image_service.requests.get', get)
    service.start(['rest', 'music'])
    assert post.call_count == 0
    result = service.statuses(['rest', 'music'])
    assert post.call_count == get.call_count == 2
    assert all(v['status'] == 'running' for v in result.values())
