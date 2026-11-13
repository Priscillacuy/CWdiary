import base64
import io
from unittest.mock import Mock

from PIL import Image
from test_app import app, auth
from image_service import ImageService


def test_username_password_registration_and_profile(app):
    c=app.test_client(); token=c.get('/api/session').json['csrf']
    result=c.post('/api/register',headers={'X-CSRF-Token':token},json={'username':'new-reader','password':'hello-world-123'})
    assert result.status_code==201 and result.json['user']['nickname']=='new-reader'
    h={'X-CSRF-Token':result.json['csrf']}
    for body in ({'gender':'guess'},{'language':'xx'},{'avatar':'../../private'}):
        assert c.patch('/api/profile',headers=h,json=body).status_code==400
    result=c.patch('/api/profile',headers=h,json={'nickname':'Sunny','gender':'male','language':'en','avatar':'fox'})
    assert result.status_code==200
    assert result.json['user']['gender']=='male' and result.json['user']['language']=='en'
    assert result.json['user']['avatar_url']=='/static/images/avatars/watercolor-fox.webp'
    assert 'password_hash' not in result.json['user'] and 'auth_version' not in result.json['user']


def test_password_change_revokes_other_sessions(app):
    a,b=app.test_client(),app.test_client();h=auth(a)
    token=b.get('/api/session').json['csrf']
    assert b.post('/api/login',headers={'X-CSRF-Token':token},json={'username':'alice','password':'password123'}).status_code==200
    payload={'old_password':'wrong-password','new_password':'new-password-123','confirm_password':'new-password-123'}
    assert a.post('/api/password',headers=h,json=payload).status_code==400
    payload.update(old_password='password123',confirm_password='mismatch123')
    assert a.post('/api/password',headers=h,json=payload).status_code==400
    payload['confirm_password']='new-password-123'
    changed=a.post('/api/password',headers=h,json=payload)
    assert changed.status_code==200 and changed.json['csrf']!=h['X-CSRF-Token']
    assert a.get('/api/entries').status_code==200
    assert b.get('/api/entries').status_code==401
    token=b.get('/api/session').json['csrf']
    assert b.post('/api/login',headers={'X-CSRF-Token':token},json={'username':'alice','password':'password123'}).status_code==401
    assert b.post('/api/login',headers={'X-CSRF-Token':token},json={'username':'alice','password':'new-password-123'}).status_code==200


def test_avatar_upload_validates_image_and_is_private(app):
    a,b=app.test_client(),app.test_client();ha,hb=auth(a),auth(b,'bob')
    assert a.post('/api/avatar',headers=ha,json={'image':'data:image/png;base64,invalid'}).status_code==400
    image=io.BytesIO();Image.new('RGB',(400,300),'#c0aa84').save(image,'PNG')
    result=a.post('/api/avatar',headers=ha,json={'image':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()})
    assert result.status_code==200
    picture=a.get(result.json['user']['avatar_url']);assert picture.status_code==200
    assert Image.open(io.BytesIO(picture.data)).size==(256,256)
    assert b.get('/api/avatar').status_code==404
    assert a.post('/api/avatar',headers=ha,json=[]).status_code==400


def test_ledger_totals_edit_delete_isolation(app):
    a,b=app.test_client(),app.test_client();ha,hb=auth(a),auth(b,'bob')
    body=dict(kind='expense',amount='12.35',category='餐饮',note='测试',entry_date='2026-11-13')
    created=a.post('/api/ledger',headers=ha,json=body);assert created.status_code==201
    item_id=created.json['id']
    assert a.post('/api/ledger',headers=ha,json={**body,'kind':'income','amount':'100.10'}).status_code==201
    report=a.get('/api/ledger?month=2026-11').json
    assert report['expense_cents']==1235 and report['income_cents']==10010
    assert b.get('/api/ledger?month=2026-11').json['items']==[]
    assert b.delete(f'/api/ledger/{item_id}',headers=hb).status_code==404
    assert b.put(f'/api/ledger/{item_id}',headers=hb,json=body).status_code==404
    assert a.put(f'/api/ledger/{item_id}',headers=ha,json={**body,'amount':'10.01'}).status_code==200
    assert a.get('/api/ledger?month=2026-11').json['expense_cents']==1001
    for amount in ('-1','NaN','Infinity','1.001'):
        assert a.post('/api/ledger',headers=ha,json={**body,'amount':amount}).status_code==400
    assert a.delete(f'/api/ledger/{item_id}',headers=ha).status_code==200


def test_ledger_daily_filter_and_totals(app):
    c=app.test_client();h=auth(c)
    body=dict(kind='expense',amount='12.35',category='餐饮',entry_date='2026-11-12')
    assert c.post('/api/ledger',headers=h,json=body).status_code==201
    assert c.post('/api/ledger',headers=h,json={**body,'entry_date':'2026-11-13','amount':'5.00'}).status_code==201
    assert c.post('/api/ledger',headers=h,json={**body,'entry_date':'2026-11-13','kind':'income','amount':'20.00'}).status_code==201
    report=c.get('/api/ledger?date=2026-11-13').json
    assert len(report['items'])==2 and report['expense_cents']==500 and report['income_cents']==2000
    assert c.get('/api/ledger?date=2026-11-14').json['items']==[]
    assert c.get('/api/ledger?month=2026-11').json['expense_cents']==1735
    for value in ('','2026-02-30','2026-11','2026-1-1'):
        assert c.get('/api/ledger?date='+value).status_code==400


def test_gender_images_have_separate_caches_and_match_profile(app,monkeypatch):
    c=app.test_client();h=auth(c)
    services=app.extensions['profile_images']
    assert len({s.path('yoga','image') for s in services.values()})==3
    monkeypatch.setattr('image_service.requests.post',Mock(return_value=Mock(status_code=200,json=lambda:{'status':'succeeded','results':[{'url':'https://cdn.example/image.png'}]})))
    image=io.BytesIO();Image.new('RGB',(20,20)).save(image,'PNG')
    for gender in ('male','female'):
        service=services[gender];service.key='test-key'
        monkeypatch.setattr(service,'_download',lambda _:image.getvalue())
        c.patch('/api/profile',headers=h,json={'gender':gender})
        c.post('/api/activity-images',headers=h,json={'categories':['yoga']})
        service.pool.shutdown(wait=True)
        status=c.get('/api/activity-images?categories=yoga').json['images']['yoga']
        assert status['status']=='succeeded' and f'profile={gender}' in status['url']
        assert c.get(status['url']).status_code==200
    assert c.get('/api/activity-images/yoga/file?profile=male').status_code==404
    service=ImageService(app.instance_path,gender='neutral')
    assert service.gender=='neutral'
    service.pool.shutdown(wait=True)


def test_register_uses_selected_language(app):
    c=app.test_client();token=c.get('/api/session').json['csrf']
    response=c.post('/api/register',headers={'X-CSRF-Token':token},json={'username':'english-reader','password':'password123','language':'en'})
    assert response.status_code==201 and response.json['user']['language']=='en'


def test_review_profile_language_and_cache_invalidation(app,monkeypatch):
    import json
    from test_app import entry
    c=app.test_client();h=auth(c);eid=entry(c,h).json['entry']['id']
    c.patch('/api/profile',headers=h,json={'gender':'male','language':'en'})
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-key')
    result=dict(emotions=['Calm'],summary='Take a quiet break.',food='Eat as needed.',vitamins='Choose varied foods.',movement='Move gently.',inspiration='Warm light',activity_plan=[dict(title='A gentle moment of seated stretching',description='Take your time to stretch gently while sitting in a comfortable position. Keep breathing naturally and stop whenever you prefer.',duration_minutes=5,category='rest',activity_id='rest') for _ in range(3)])
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps(result)}}]}))
    monkeypatch.setattr('app.requests.post',post)
    response=c.post('/api/analyze',headers=h,json={'entry_id':eid,'consent':True})
    assert response.status_code==200
    assert response.json['analysis']['disclaimer'].startswith('For everyday')
    prompt=post.call_args.kwargs['json']['messages'][0]['content']
    assert 'male' in prompt and 'must be in English' in prompt
    assert c.get(f'/api/entries/{eid}').json['analysis'] is not None
    c.patch('/api/profile',headers=h,json={'gender':'female'})
    assert c.get(f'/api/entries/{eid}').json['analysis'] is None
    assert c.post('/api/analyze',headers=h,json={'entry_id':eid,'consent':True}).status_code==200
    assert post.call_count==2


def test_legacy_database_migration_preserves_users(tmp_path):
    import sqlite3
    from app import create_app
    path=tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,nickname TEXT NOT NULL,password_hash TEXT NOT NULL)')
        connection.execute("INSERT INTO users VALUES(1,'legacy','原有昵称','unchanged-hash')")
    migrated=create_app({'TESTING':True,'DATABASE':str(path),'SECRET_KEY':'test-secret'})
    with sqlite3.connect(path) as connection:
        row=connection.execute('SELECT nickname,password_hash,gender,language,avatar,auth_version FROM users WHERE id=1').fetchone()
        assert row==('原有昵称','unchanged-hash','','zh','cat',0)
