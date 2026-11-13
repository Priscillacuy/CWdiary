import json
import sqlite3
from unittest.mock import Mock

import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'test.sqlite3'), 'SECRET_KEY': 'test-secret'})


def auth(client, username='alice'):
    token = client.get('/api/session').json['csrf']
    response = client.post('/api/register', json={'username': username, 'nickname': '小隅', 'password': 'password123'}, headers={'X-CSRF-Token': token})
    assert response.status_code == 201
    return {'X-CSRF-Token': response.json['csrf']}


def entry(client, headers, **kwargs):
    payload = dict(title='阳光', content='今天散步，晒了太阳。', mood='开心', tags=['生活'], entry_date='2026-11-11')
    payload.update(kwargs)
    return client.post('/api/entries', headers=headers, json=payload)


def test_auth_and_csrf(app):
    c = app.test_client()
    assert c.get('/api/entries').status_code == 401
    assert c.post('/api/register', json={}).status_code == 403
    h = auth(c)
    assert entry(c, h).status_code == 201
    assert c.patch('/api/profile', headers=h, json={'nickname': '新昵称'}).json['user']['nickname'] == '新昵称'
    c.post('/api/logout', headers=h)
    token = c.get('/api/session').json['csrf']
    assert c.post('/api/login', json={'username': 'alice', 'password': 'wrong-password'}, headers={'X-CSRF-Token': token}).status_code == 401
    r = c.post('/api/login', json={'username': 'alice', 'password': 'password123'}, headers={'X-CSRF-Token': token})
    assert r.status_code == 200
    assert c.get('/api/entries').json['total'] == 1


def test_crud_isolation_filters(app):
    a, b = app.test_client(), app.test_client()
    ha, hb = auth(a), auth(b, 'bob')
    r = entry(a, ha)
    eid = r.json['entry']['id']
    for method in ('get', 'put', 'delete'):
        assert getattr(b, method)(f'/api/entries/{eid}', headers=hb, json={}).status_code == 404
    assert b.get('/api/overview').json['total'] == 0
    assert a.get('/api/entries?tag=生活&q=太阳&mood=开心&start=2026-11-01').json['total'] == 1
    assert a.get('/api/entries?tag=生').json['total'] == 0
    assert a.get('/api/entries?date=2026-11-10').json['total'] == 0
    assert a.get('/api/entries?start=bad').status_code == 400
    assert a.get('/api/entries?offset=bad').status_code == 400
    assert a.put(f'/api/entries/{eid}', headers=ha, json=dict(title='雨天', content='听雨。', mood='平静', tags=[], entry_date='2026-11-10')).status_code == 200
    assert a.get('/api/overview').json['days'] == [{'date':'2026-11-10','score':3.0,'count':1}]
    assert a.delete(f'/api/entries/{eid}', headers=ha).status_code == 200
    assert a.get('/api/entries').json['total'] == 0


def test_validation_persistence(app):
    c=app.test_client(); h=auth(c)
    for values in ({'content':''},{'mood':'bad'},{'entry_date':'2026-02-30'},{'tags':['x']*6},{'title':'x'*101}):
        assert entry(c,h,**values).status_code == 400
    assert c.post('/api/entries', headers=h, json=[]).status_code == 400
    entry(c,h)
    with sqlite3.connect(app.config['DATABASE']) as conn:
        assert conn.execute('SELECT count(*) FROM entries').fetchone()[0] == 1
        assert conn.execute('SELECT password_hash FROM users').fetchone()[0].startswith('pbkdf2:')


def test_ai_consent_cache_and_errors(app, monkeypatch):
    c=app.test_client();h=auth(c);eid=entry(c,h).json['entry']['id']
    assert c.post('/api/analyze',headers=h,json={'entry_id':eid}).status_code == 400
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake-test-key')
    result=dict(emotions=['开心'], summary='有满足感。', food='规律吃饭。', vitamins='均衡饮食。', movement='轻松散步。', inspiration='自然纪录片', activity_plan=[dict(title='休息一下', description='坐下喝点水。', duration_minutes=10, category='rest', activity_id='rest'), dict(title='听歌', description='听喜欢的轻音乐。', duration_minutes=15, category='music', activity_id='music'), dict(title='轻柔瑜伽', description='舒适范围内伸展，不适就停。', duration_minutes=10, category='yoga', activity_id='yoga')])
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps(result)}}]}))
    monkeypatch.setattr('app.requests.post',post)
    payload={'entry_id':eid,'consent':True}
    r=c.post('/api/analyze',headers=h,json=payload)
    assert r.status_code == 200
    assert '专业意见' in r.json['analysis']['disclaimer']
    assert r.json['analysis']['activity_plan'] == result['activity_plan']
    assert c.get(f'/api/entries/{eid}').json['analysis']['summary'] == result['summary']
    assert c.post('/api/analyze',headers=h,json=payload).status_code == 200
    assert post.call_count == 1
    c.put(f'/api/entries/{eid}',headers=h,json=dict(title='更新',content='今天休息。',mood='平静',tags=[],entry_date='2026-11-11'))
    assert c.get(f'/api/entries/{eid}').json['analysis'] is None
    post.return_value=Mock(status_code=402)
    assert '余额不足' in c.post('/api/analyze',headers=h,json=payload).json['error']
    assert c.post('/api/analyze',headers=h,json={'start':'2026-11-12','end':'2026-11-11','consent':True}).status_code == 400
    post.return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':'not json'}}]})
    assert c.post('/api/analyze',headers=h,json=payload).status_code == 502


def test_save_without_title_and_analyze_failure_preserves_entry(app, monkeypatch):
    c = app.test_client()
    h = auth(c)
    payload = dict(content='只写正文也应该能保存。', mood='平静', tags=[], entry_date='2026-11-12')
    saved = c.post('/api/entries', headers=h, json=payload)
    assert saved.status_code == 201
    eid = saved.json['entry']['id']
    assert saved.json['entry']['title'] == '2026-11-12 的日记'
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'fake-test-key')
    monkeypatch.setattr('app.requests.post', Mock(return_value=Mock(status_code=402)))
    failed = c.post('/api/analyze', headers=h, json={'entry_id': eid, 'consent': True})
    assert failed.status_code == 502
    persisted = c.get(f'/api/entries/{eid}').json
    assert persisted['entry']['content'] == payload['content']
    assert persisted['analysis'] is None
    payload.update(title='   ', content='编辑后仍可以不填标题。')
    assert c.put(f'/api/entries/{eid}', headers=h, json=payload).status_code == 200
    assert c.get('/api/entries').json['total'] == 1


@pytest.mark.parametrize('durations', [[0, 10, 15], [True, 10, 15], [61, 10, 15], [60, 60, 60, 60]])
def test_reject_invalid_activity_plan(app, monkeypatch, durations):
    c=app.test_client(); h=auth(c); eid=entry(c,h).json['entry']['id']
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake-test-key')
    result=dict(emotions=['平静'], summary='慢慢来。', food='规律饮食。', vitamins='均衡饮食。', movement='散步。', inspiration='风景', activity_plan=[dict(title='休息', description='坐一会。', duration_minutes=d, category='rest') for d in durations])
    monkeypatch.setattr('app.requests.post', Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps(result)}}]})))
    assert c.post('/api/analyze', headers=h, json={'entry_id':eid,'consent':True}).status_code == 502
    assert c.get(f'/api/entries/{eid}').json['analysis'] is None
