import json
from unittest.mock import Mock

import pytest

from audio_service import AudioService, closing, guidance
from language_support import localized_text
from test_app import app, auth, entry


@pytest.mark.parametrize('language', ['zh-HK', 'zh-TW'])
def test_traditional_locale_registration_profile_and_login(app, language):
    c = app.test_client()
    token = c.get('/api/session').json['csrf']
    response = c.post('/api/register', headers={'X-CSRF-Token': token}, json={
        'username': 'regional-reader', 'password': 'password123', 'language': language})
    assert response.status_code == 201 and response.json['user']['language'] == language
    h = {'X-CSRF-Token': response.json['csrf']}
    other = 'zh-TW' if language == 'zh-HK' else 'zh-HK'
    assert c.patch('/api/profile', headers=h, json={'language': other}).json['user']['language'] == other
    assert c.get('/api/session').json['user']['language'] == other
    c.post('/api/logout', headers=h)
    token = c.get('/api/session').json['csrf']
    logged = c.post('/api/login', headers={'X-CSRF-Token': token}, json={
        'username': 'regional-reader', 'password': 'password123'})
    assert logged.json['user']['language'] == other


@pytest.mark.parametrize('language,region', [('zh-HK', '中國香港'), ('zh-TW', '中國台灣')])
def test_review_uses_regional_traditional_and_invalidates_cache(app, monkeypatch, language, region):
    c = app.test_client(); h = auth(c); eid = entry(c, h).json['entry']['id']
    c.patch('/api/profile', headers=h, json={'language': language})
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    result = dict(emotions=['轻松'], summary='让身体放松。', food='按需要吃饭。',
                  vitamins='选择多样食物。', movement='轻轻伸展。', inspiration='温暖光线',
                  activity_plan=[dict(title='听音乐', description='选择喜欢的音乐。',
                                      duration_minutes=5, category='rest', activity_id='rest') for _ in range(3)])
    post = Mock(return_value=Mock(status_code=200, json=lambda: {
        'choices': [{'message': {'content': json.dumps(result)}}]}))
    monkeypatch.setattr('app.requests.post', post)
    response = c.post('/api/analyze', headers=h, json={'entry_id': eid, 'consent': True})
    assert response.status_code == 200
    assert region in post.call_args.kwargs['json']['messages'][0]['content']
    assert response.json['analysis']['summary'] == '讓身體放鬆。'
    assert response.json['analysis']['activity_plan'][0]['title'] == '聽音樂'
    assert '僅供' in response.json['analysis']['disclaimer']
    c.patch('/api/profile', headers=h, json={'language': 'zh'})
    assert c.get(f'/api/entries/{eid}').json['analysis'] is None


def test_traditional_guidance_and_tts_language_code(tmp_path, monkeypatch):
    assert localized_text('软件与鼠标', 'zh-TW') == '軟體與滑鼠'
    step = dict(activity_id='rest', category='rest', title='安静休息', description='放松身体。', duration_seconds=300)
    assert '跟住我哋' in guidance(step, 'zh-HK')
    assert '好夢' in closing('zh-TW', 'sleep')
    service = AudioService(tmp_path)
    post = Mock()
    monkeypatch.setattr(service, '_post_audio', post)
    service.speech('讓我們放鬆。', 'female', 'zh-TW')
    assert post.call_args.args[1]['language_code'] == 'zh'
    service.pool.shutdown(wait=True)
