import json
from unittest.mock import Mock

from activity_catalog import CATALOG, BY_ID
from test_app import app, auth, entry


def test_catalog_complete_and_gallery(app):
    assert len(CATALOG) == len(BY_ID) == 50
    assert len({item['name'] for item in CATALOG}) == 50
    assert all(5 <= item['duration_minutes'] <= 30 and item['image_prompt'] and item['suitable_for'] and item['instructions'] for item in CATALOG)
    c = app.test_client()
    assert c.get('/activity-library').status_code == 404
    auth(c)
    assert c.get('/activity-library').status_code == 404
    assert 'activity_library' not in c.get('/api/session').json
    assert c.get('/static/data/relaxation-activities.json').status_code == 404
    assert b'href="/activity-library"' not in c.get('/').data


def test_review_selects_library_image(app, monkeypatch):
    c=app.test_client();h=auth(c);eid=entry(c,h).json['entry']['id']
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-key')
    plan=[dict(title='看看窗外的云',description='安全舒适地坐一会儿。',duration_minutes=10,category='rest',activity_id='cloud_watch'),dict(title='随手涂鸦',description='随意画几笔。',duration_minutes=10,category='read',activity_id='free_doodle'),dict(title='听喜欢的歌',description='调低音量。',duration_minutes=5,category='music',activity_id='favorite_song')]
    result=dict(emotions=['平静'],summary='放慢节奏。',food='按需进食。',vitamins='均衡饮食。',movement='舒适活动。',inspiration='自然光',activity_plan=plan)
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'choices':[{'message':{'content':json.dumps(result)}}]}))
    monkeypatch.setattr('app.requests.post',post)
    response=c.post('/api/analyze',headers=h,json={'entry_id':eid,'consent':True})
    assert response.status_code == 200
    chosen=response.json['analysis']['activity_plan']
    assert [step['activity_id'] for step in chosen] == ['cloud_watch','free_doodle','favorite_song']
    assert chosen[0]['category'] == 'walk'
    assert 'cloud_watch' in post.call_args.kwargs['json']['messages'][0]['content']
    assert c.get(f'/api/entries/{eid}').json['analysis']['activity_plan'] == chosen
