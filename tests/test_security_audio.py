import json
import sqlite3
from unittest.mock import Mock

from werkzeug.security import check_password_hash

from audio_service import AudioError, AudioService, closing, guidance, session_steps
from test_app import app, auth, entry


def test_canonical_username_uniqueness_and_safe_password_storage(app):
    a,b=app.test_client(),app.test_client()
    auth(a,'Reader')
    token=b.get('/api/session').json['csrf'];h={'X-CSRF-Token':token}
    for username in ('Reader','reader',' READER ','Ｒｅａｄｅｒ'):
        assert b.post('/api/register',headers=h,json={'username':username,'password':'different-pass'}).status_code==409
    # Separate users may intentionally choose the same password, with different salts.
    assert b.post('/api/register',headers=h,json={'username':'another-reader','password':'password123'}).status_code==201
    with sqlite3.connect(app.config['DATABASE']) as connection:
        hashes=[r[0] for r in connection.execute('SELECT password_hash FROM users')]
        assert len(hashes)==2 and hashes[0]!=hashes[1]
        assert all(check_password_hash(value,'password123') for value in hashes)
    assert a.post('/api/logout',headers={'X-CSRF-Token':a.get('/api/session').json['csrf']}).status_code==200
    h={'X-CSRF-Token':a.get('/api/session').json['csrf']}
    assert a.post('/api/login',headers=h,json={'username':'  READER  ','password':'password123'}).status_code==200


def test_password_history_prevents_reuse(app):
    c=app.test_client();h=auth(c)
    def change(old,new):
        nonlocal h
        result=c.post('/api/password',headers=h,json={'old_password':old,'new_password':new,'confirm_password':new})
        if result.status_code==200:h={'X-CSRF-Token':result.json['csrf']}
        return result
    assert change('password123','password123').status_code==400
    assert change('password123','second-secret-123').status_code==200
    assert change('second-secret-123','third-secret-123').status_code==200
    assert change('third-secret-123','password123').status_code==400
    assert change('third-secret-123','second-secret-123').status_code==400
    assert change('third-secret-123','fourth-secret-123').status_code==200


def stored_analysis(app,c,h):
    eid=entry(c,h).json['entry']['id']
    plan=[dict(title='休息',description='坐一会。',duration_minutes=5,category='rest',activity_id='rest'),dict(title='听音乐',description='慢慢来。',duration_minutes=5,category='music',activity_id='music'),dict(title='看书',description='按精力调整。',duration_minutes=5,category='read',activity_id='read')]
    with sqlite3.connect(app.config['DATABASE']) as connection:
        aid=connection.execute('INSERT INTO analyses(user_id,entry_id,fingerprint,result,profile_key) VALUES(?,?,?,?,?)',(c.get('/api/session').json['user']['id'],eid,'audio-test',json.dumps({'activity_plan':plan}),'neutral:zh')).lastrowid
    return aid,plan


def test_audio_truncation_and_matching_recommendation_narration():
    plan=[dict(title='Displayed recommendation',description='Only the displayed instructions.',category='rest',activity_id='rest',duration_minutes=5),dict(title='Music',description='Listen quietly.',category='music',activity_id='music',duration_minutes=10)]
    steps=session_steps(plan,7,'zh')
    assert [s['duration_seconds'] for s in steps]==[300,120]
    assert 'Displayed recommendation' in steps[0]['text'] and 'Only the displayed instructions.' in steps[0]['text']
    assert '2分钟' in steps[1]['text']
    assert '好梦' in closing('zh','sleep') and '过得开心' in closing('zh','day')
    assert 'sweet dreams' in closing('en','sleep')
    assert 'Chinese' not in guidance({'activity_id':'cloud_watch','category':'walk','duration_seconds':60},'en')
    assert 'cloud' in guidance({'activity_id':'cloud_watch','category':'walk','duration_seconds':60},'en').lower()


def test_private_audio_prepare_cache_range_and_isolation(app,monkeypatch):
    a,b=app.test_client(),app.test_client();ha,hb=auth(a),auth(b,'bob');aid,plan=stored_analysis(app,a,ha)
    service=app.extensions['relaxation_audio']
    monkeypatch.setattr(service,'translated_steps',lambda steps,source,target:steps)
    service.key='test-audio-key'
    (service.directory/'music/daylight.m4a').write_bytes(b'fake music')
    post=Mock(return_value=Mock(status_code=200,content=b'ID3'+b'a'*500))
    monkeypatch.setattr('audio_service.requests.post',post)
    body={'analysis_id':aid,'minutes':7,'voice':'female','mode':'day','consent':True}
    assert a.post('/api/relaxation/prepare',headers=ha,json={**body,'consent':False}).status_code==400
    for values in ({'minutes':True},{'minutes':0},{'minutes':16},{'voice':'unknown'},{'analysis_id':True},{'mode':'unknown'}):
        assert a.post('/api/relaxation/prepare',headers=ha,json={**body,**values}).status_code==400
    assert b.post('/api/relaxation/prepare',headers=hb,json=body).status_code==404
    created=a.post('/api/relaxation/prepare',headers=ha,json=body);assert created.status_code==202
    service.pool.shutdown(wait=True)
    sid=created.json['session_id'];url='/api/relaxation/sessions/'+sid
    status=a.get(url).json
    assert status['status']=='ready'
    assert [s['duration_seconds'] for s in status['steps']]==[300,120]
    assert 'speech' not in json.dumps(status)
    assert all(call.kwargs['json']['model_id']=='eleven_v4_turbo' for call in post.call_args_list)
    assert a.get(status['music_url']).status_code==200
    assert a.get(status['steps'][0]['voice_url'],headers={'Range':'bytes=0-99'}).status_code==206
    assert a.get(url+'/voice/100').status_code==404
    assert b.get(url).status_code==404 and b.get(status['music_url']).status_code==404
    assert app.test_client().get(status['steps'][0]['voice_url']).status_code==401
    assert a.get('/static/audio-library/music/daylight.m4a').status_code==404
    assert a.post('/api/relaxation/prepare',headers=ha,json=body).status_code==202
    assert post.call_count==3  # Two steps and one ending; no repeat generation.


def test_audio_failure_is_retriable_and_no_provider_details_leak(tmp_path,monkeypatch):
    service=AudioService(tmp_path/'audio');service.key='private-key'
    monkeypatch.setattr(service,'translated_steps',lambda steps,source,target:steps)
    (service.directory/'music/daylight.m4a').write_bytes(b'fake music')
    post=Mock(return_value=Mock(status_code=402,content=b'private upstream account information'))
    monkeypatch.setattr('audio_service.requests.post',post)
    plan=[dict(title='Rest',description='Sit comfortably.',category='rest',activity_id='rest',duration_minutes=5)]
    sid=service.prepare(1,1,plan,1,'male','en','day');service.pool.shutdown(wait=True)
    data=service.read(1,sid)
    assert data['status']=='failed' and '额度不足' in data['error']
    assert 'private' not in data['error'] and data['steps'][0]['duration_seconds']==60


def test_audio_profile_changes_require_new_review(app):
    c=app.test_client();h=auth(c);aid,_=stored_analysis(app,c,h)
    c.patch('/api/profile',headers=h,json={'language':'en'})
    assert c.post('/api/relaxation/prepare',headers=h,json={'analysis_id':aid,'minutes':5,'voice':'female','mode':'day','consent':True}).status_code==404
