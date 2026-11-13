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
