import json
import sqlite3
from unittest.mock import Mock

import pytest
import cloud_database
from app import create_app
from test_app import auth


class SQLiteTransport:
    """Execute the actual application SQL behind a small Hrana protocol fixture."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.headers = {}
        self.baton = None

    def post(self, url, json, **kwargs):
        assert url.startswith('https://test.turso.io/')
        assert json['baton'] == self.baton
        results = []
        for operation in json['requests']:
            if operation['type'] == 'close':
                assert not self.db.in_transaction
                self.baton = None
                results.append({'type': 'ok', 'response': {'type': 'close'}})
                continue
            statement = operation['stmt']
            try:
                cursor = self.db.execute(statement['sql'], [cloud_database.decode(x) for x in statement.get('args', [])])
                if not self.db.in_transaction:
                    self.db.commit()
                names = [x[0] for x in cursor.description] if cursor.description else []
                rows = cursor.fetchall() if cursor.description else []
                value = {'cols': [{'name': n} for n in names], 'rows': [[cloud_database.encode(x) for x in row] for row in rows],
                         'affected_row_count': max(0, cursor.rowcount), 'last_insert_rowid': str(cursor.lastrowid) if cursor.lastrowid else None}
                results.append({'type': 'ok', 'response': {'type': 'execute', 'result': value}})
                self.baton = 'next-baton'
            except sqlite3.IntegrityError:
                results.append({'type': 'error', 'error': {'code': 'SQLITE_CONSTRAINT_UNIQUE'}})
        return Mock(raise_for_status=lambda: None, json=lambda: {'baton': self.baton, 'results': results})

    def close(self):
        self.db.close()


def test_turso_auth_diary_ledger_and_restart_persistence(tmp_path, monkeypatch):
    remote = tmp_path / 'remote.sqlite3'
    monkeypatch.setattr(cloud_database.requests, 'Session', lambda: SQLiteTransport(remote))
    config = {'TESTING': True, 'SECRET_KEY': 'cloud-test-secret', 'DATABASE': str(tmp_path/'cache.sqlite3'),
              'TURSO_DATABASE_URL': 'libsql://test.turso.io', 'TURSO_AUTH_TOKEN': 'test-token'}
    app = create_app(config); c = app.test_client(); h = auth(c)
    body = dict(title='云端验证', content='这是一篇虚构的云端测试日记。', mood='平静', tags=['云端'], entry_date='2026-11-14')
    assert c.post('/api/entries', headers=h, json=body).status_code == 201
    assert c.post('/api/ledger', headers=h, json=dict(kind='expense', category='餐饮', amount='12.50', entry_date='2026-11-14')).status_code == 201
    assert c.get('/api/entries?tag=云端').json['total'] == 1
    assert c.get('/api/ledger/summary?date=2026-11-14').json['year']['expense_cents'] == 1250
    assert c.patch('/api/profile', headers=h, json={'currency': 'HKD'}).status_code == 200
    # A different app/cache instance must see committed remote records.
    second = create_app({**config, 'DATABASE': str(tmp_path/'different-cache.sqlite3')}).test_client()
    token = second.get('/api/session').json['csrf']
    assert second.post('/api/login', headers={'X-CSRF-Token': token}, json={'username':'alice', 'password':'password123'}).status_code == 200
    assert second.get('/api/entries').json['total'] == 1
    assert second.get('/api/ledger?date=2026-11-14&currency=CNY').json['expense_cents'] == 1250


def test_turso_rollback_and_constraint_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_database.requests, 'Session', lambda: SQLiteTransport(tmp_path/'rollback.sqlite3'))
    db = cloud_database.Connection('https://test.turso.io', 'test-token')
    db.execute('CREATE TABLE example(id INTEGER PRIMARY KEY,value TEXT UNIQUE)')
    db.execute('INSERT INTO example(value) VALUES(?)', ('one',)); db.commit()
    db.execute('INSERT INTO example(value) VALUES(?)', ('two',))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO example(value) VALUES(?)', ('one',))
    db.rollback()
    assert [r[0] for r in db.execute('SELECT value FROM example')] == ['one']
    db.close()


def test_unconfigured_vercel_serves_frontend_without_accepting_ephemeral_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('VERCEL', '1'); monkeypatch.setenv('APP_INSTANCE_PATH', str(tmp_path))
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret', 'TURSO_DATABASE_URL':'', 'TURSO_AUTH_TOKEN':''})
    c = app.test_client()
    assert c.get('/').status_code == 200
    assert c.get('/static/js/app.js').status_code == 200
    assert c.get('/healthz').status_code == 503
    assert c.post('/api/register', json={'username':'cloud-user','password':'test-password123'}).status_code == 503
    assert not (tmp_path/'diary.sqlite3').exists()


def test_frontend_build_copies_only_static_assets(tmp_path):
    from pathlib import Path
    config = json.loads(Path('vercel.json').read_text())
    assert config['framework'] == 'flask'
    assert 'wsgi:app' in Path('pyproject.toml').read_text()
    assert 'instance' in Path('.vercelignore').read_text()


def test_private_files_and_worker_leases_survive_cache_changes(tmp_path, monkeypatch):
    assert cloud_database.decode({'type':'blob', 'base64':'eA'}) == b'x'
    from cloud_files import FileStore
    remote = tmp_path/'files.sqlite3'
    monkeypatch.setattr(cloud_database.requests, 'Session', lambda: SQLiteTransport(remote))
    first = FileStore(tmp_path/'first', 'https://test.turso.io', 'test-token')
    second = FileStore(tmp_path/'second', 'https://test.turso.io', 'test-token')
    path = first.root/'avatars'/'test.png'; path.parent.mkdir(parents=True); path.write_bytes(b'synthetic-image')
    first.upload(path)
    restored = second.load(second.root/'avatars'/'test.png')
    assert restored.read_bytes() == b'synthetic-image'
    with first.lease(first.root/'job.lock') as acquired:
        assert acquired
        with second.lease(second.root/'job.lock') as duplicate:
            assert not duplicate
    with second.lease(second.root/'job.lock') as acquired:
        assert acquired
    with pytest.raises(ValueError):
        second.load(tmp_path/'outside-root')


def test_cloud_audio_resumes_one_unit_per_request_without_background_threads(tmp_path, monkeypatch):
    from audio_service import AudioService
    from cloud_files import FileStore
    from activity_catalog import DEFAULT_IDS
    remote = tmp_path/'audio.sqlite3'
    monkeypatch.setattr(cloud_database.requests, 'Session', lambda: SQLiteTransport(remote))
    plan = [dict(activity_id=DEFAULT_IDS['rest'], category='rest', title='休息', description='坐一会儿。', duration_minutes=1)]
    states = []
    for phase in range(5):
        root = tmp_path/('instance-'+str(phase))
        service = AudioService(root/'audio-library')
        service.file_store = FileStore(root, 'https://test.turso.io', 'test-token')
        monkeypatch.setattr(service, 'translated_steps', lambda steps, source, target: steps)
        monkeypatch.setattr(service, '_post_audio', lambda endpoint, body, path, **kwargs: path.write_bytes(b'ID3synthetic'))
        monkeypatch.setattr(service.pool, 'submit', lambda *args, **kwargs: pytest.fail('Cloud work must run inside requests'))
        sid = service.prepare(1, 7, plan, 1, 'female', 'zh', 'day')
        state = service.public(1, sid); states.append(state['status'])
    assert states == ['preparing', 'preparing', 'preparing', 'ready', 'ready']
    assert service.ready_files(service.read(1, sid))


def test_cloud_image_generation_does_not_submit_detached_work(tmp_path, monkeypatch):
    from image_service import ImageService
    from cloud_files import FileStore
    from activity_catalog import DEFAULT_IDS
    remote = tmp_path/'images.sqlite3'
    monkeypatch.setattr(cloud_database.requests, 'Session', lambda: SQLiteTransport(remote))
    service = ImageService(tmp_path/'cache'/'images')
    service.file_store = FileStore(tmp_path/'cache', 'https://test.turso.io', 'test-token')
    service.key = 'fake-test-key'
    monkeypatch.setattr(service.pool, 'submit', lambda *args, **kwargs: pytest.fail('Detached worker submitted'))
    def generate(category, *args):
        service.path(category, 'image').write_bytes(b'synthetic-image')
        service.file_store.upload(service.path(category, 'image'))
        service._write(category, {'status':'succeeded'})
    monkeypatch.setattr(service, '_generate', generate)
    category = DEFAULT_IDS['rest']
    assert service.start([category])[category]['status'] == 'succeeded'
    other = ImageService(tmp_path/'different'/'images')
    other.file_store = FileStore(tmp_path/'different', 'https://test.turso.io', 'test-token')
    assert other.statuses([category])[category]['status'] == 'succeeded'
