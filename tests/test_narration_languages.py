import json
from unittest.mock import Mock

import pytest

from audio_service import AudioError, AudioService, session_steps
from test_app import app, auth
from test_security_audio import stored_analysis


@pytest.mark.parametrize('locale,code', [('zh','zh'), ('zh-HK','yue'), ('zh-TW','zh'), ('en','en')])
def test_narration_passes_actual_spoken_language(tmp_path, monkeypatch, locale, code):
    service = AudioService(tmp_path)
    post = Mock()
    monkeypatch.setattr(service, '_post_audio', post)
    service.speech('A short test.', 'male', locale)
    assert post.call_args.args[1]['language_code'] == code
    service.pool.shutdown(wait=True)


def test_translation_only_changes_copy_not_timing_or_ids(tmp_path, monkeypatch):
    service = AudioService(tmp_path)
    plan = [dict(title='休息', description='舒服地坐下，不舒服就停。', duration_minutes=5, category='rest', activity_id='rest')]
    steps = session_steps(plan, 2, 'en')
    post = Mock(return_value=Mock(status_code=200, json=lambda: {'choices':[{'message':{'content':json.dumps({
        'steps':[{'title':'Rest gently', 'description':'Sit comfortably. Stop if uncomfortable.', 'duration_seconds':999}]})}}]}))
    monkeypatch.setenv('DEEPSEEK_API_KEY','test')
    monkeypatch.setattr('audio_service.requests.post',post)
    result = service.translated_steps(steps, 'zh', 'en')
    assert result[0]['duration_seconds'] == 120 and result[0]['activity_id'] == 'rest'
    assert 'Sit comfortably. Stop if uncomfortable.' in result[0]['text']
    sent = json.loads(post.call_args.kwargs['json']['messages'][1]['content'])
    assert sent == {'steps':[{'title':'休息','description':'舒服地坐下，不舒服就停。'}]}
    service.pool.shutdown(wait=True)


@pytest.mark.parametrize('language', ['zh', 'zh-HK', 'zh-TW', 'en'])
def test_same_language_written_copy_is_rewritten_for_speech(tmp_path, monkeypatch, language):
    service=AudioService(tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY','test')
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps({
        'steps':[{'title':'坐着歇一会儿','description':'找个舒服的位置坐下。不舒服就停。'}]})}}]}))
    monkeypatch.setattr('audio_service.requests.post',post)
    plan=[dict(title='进行静态休息',description='采用舒适坐姿，若有不适应立即停止。',duration_minutes=5,category='rest',activity_id='rest')]
    result=service.translated_steps(session_steps(plan,1,language),language,language)
    assert post.call_count==1
    prompt=post.call_args.kwargs['json']['messages'][0]['content']
    assert 'EVEN WHEN source and target languages are the same' in prompt
    assert 'Preserve every instruction, qualification and safety limit' in prompt
    assert result[0]['duration_seconds']==60 and result[0]['activity_id']=='rest'
    assert '进行静态休息' not in result[0]['text']
    assert plan[0]['description']=='采用舒适坐姿，若有不适应立即停止。'
    service.pool.shutdown(wait=True)


def test_translation_failure_cannot_play_wrong_language(tmp_path, monkeypatch):
    service = AudioService(tmp_path)
    (service.directory/'music/daylight.m4a').write_bytes(b'fake music')
    monkeypatch.setenv('DEEPSEEK_API_KEY','test')
    monkeypatch.setattr('audio_service.requests.post', Mock(return_value=Mock(status_code=200, json=lambda: {
        'choices':[{'message':{'content':'{"steps": []}'}}]})))
    speech = Mock(); monkeypatch.setattr(service, 'speech', speech)
    plan = [dict(title='休息', description='坐一会。', duration_minutes=5, category='rest', activity_id='rest')]
    sid = service.prepare(1,1,plan,1,'female','en','day',source_language='zh')
    service.pool.shutdown(wait=True)
    assert service.read(1,sid)['status'] == 'failed' and not speech.called


def test_cantonese_copy_is_translated_to_mandarin(tmp_path, monkeypatch):
    service=AudioService(tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY','test')
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps({
        'steps':[{'title':'安靜休息','description':'找個舒服的位置坐下，不舒服就停止。'}]})}}]}))
    monkeypatch.setattr('audio_service.requests.post',post)
    steps=session_steps([dict(title='休息',description='坐低，唔舒服就停。',duration_minutes=5,category='rest',activity_id='rest')],1,'zh-TW')
    result=service.translated_steps(steps,'zh-HK','zh-TW')
    assert '坐下' in result[0]['text'] and '唔舒服' not in result[0]['text']
    assert '自然國語' in post.call_args.kwargs['json']['messages'][0]['content']
    service.pool.shutdown(wait=True)


@pytest.mark.parametrize('language', ['zh', 'zh-HK', 'zh-TW', 'en'])
def test_route_uses_selected_narration_language_without_changing_account(app, monkeypatch, language):
    c=app.test_client();h=auth(c);aid,plan=stored_analysis(app,c,h)
    service=app.extensions['relaxation_audio']
    post=Mock(return_value=Mock(status_code=200,content=b'ID3'+b'a'*500))
    monkeypatch.setattr('audio_service.requests.post',post)
    (service.directory/'music/daylight.m4a').write_bytes(b'fake music')
    translator=Mock(side_effect=lambda steps,source,target:steps)
    monkeypatch.setattr(service,'translated_steps',translator)
    response=c.post('/api/relaxation/prepare',headers=h,json={
        'analysis_id':aid,'minutes':1,'voice':'female','mode':'day','consent':True,'language':language})
    assert response.status_code==202 and response.json['language']==language
    service.pool.shutdown(wait=True)
    assert translator.call_args.args[1:] == ('zh',language)
    assert c.get('/api/session').json['user']['language']=='zh'
    assert post.call_args.kwargs['json']['language_code']=={'zh-HK':'yue','en':'en'}.get(language,'zh')
    bad=c.post('/api/relaxation/prepare',headers=h,json={
        'analysis_id':aid,'minutes':1,'voice':'female','mode':'day','consent':True,'language':'unknown'})
    assert bad.status_code==400


def test_different_narration_languages_never_share_sessions(tmp_path,monkeypatch):
    service=AudioService(tmp_path)
    monkeypatch.setattr(service.pool,'submit',Mock())
    plan=[dict(title='休息',description='坐一会。',duration_minutes=5,category='rest',activity_id='rest')]
    sessions=[service.prepare(1,1,plan,1,'female',lang,'day',source_language='zh') for lang in ('zh','zh-HK','zh-TW','en')]
    assert len(set(sessions))==4
    service.pool.shutdown(wait=True)
