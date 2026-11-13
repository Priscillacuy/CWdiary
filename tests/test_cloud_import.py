import copy
import sqlite3

import pytest
from app import create_app
from test_app import auth, entry
from scripts.import_local_to_turso import merge, read_source


def database(tmp_path, name, username):
    path = tmp_path/(name+'.sqlite3')
    app = create_app({'TESTING':True, 'DATABASE':str(path), 'SECRET_KEY':'migration-test'})
    client = app.test_client(); headers = auth(client, username)
    result = entry(client, headers)
    client.post('/api/ledger', headers=headers, json=dict(kind='expense', amount='12.50', category='测试', entry_date='2026-11-14'))
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.execute('INSERT INTO analyses(user_id,entry_id,fingerprint,result,profile_key) VALUES(1,?,?,?,?)',
               (result.json['entry']['id'], name, '{"summary":"synthetic"}', 'neutral:zh'))
    db.commit()
    return db


def test_import_remaps_ids_preserves_online_data_and_is_idempotent(tmp_path):
    source = database(tmp_path, 'local', 'alice')
    target = database(tmp_path, 'online', 'bob')
    before = dict(target.execute('SELECT * FROM entries WHERE id=1').fetchone())
    records = read_source(source)
    result = merge(records, target, 'source-1', tmp_path/'backup.json')
    assert result['inserted'] == dict(users=1, entries=1, ledger=1, analyses=1, password_history=1)
    assert dict(target.execute('SELECT * FROM entries WHERE id=1').fetchone()) == before
    imported = target.execute('SELECT * FROM entries WHERE id=2').fetchone()
    assert imported['user_id'] == 2
    assert target.execute('SELECT entry_id,user_id FROM analyses WHERE id=2').fetchone()[:] == (2,2)
    assert target.execute('SELECT password_hash FROM users WHERE id=2').fetchone()[0] == records['users'][0]['password_hash']
    again = merge(records, target, 'source-1', tmp_path/'backup-again.json')
    assert all(n == 0 for n in again['inserted'].values())
    assert all(n == 1 for n in again['reused'].values())
    assert target.execute('SELECT count(*) FROM entries').fetchone()[0] == 2


def test_matching_username_with_different_hash_is_not_merged(tmp_path):
    source = database(tmp_path, 'local', 'alice')
    target = database(tmp_path, 'online', 'alice')
    original_hash = target.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0]
    result = merge(read_source(source), target, 'source-1', tmp_path/'backup.json')
    assert result['renamed_accounts'] == [{'from':'alice','to':'alice-local'}]
    assert target.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0] == original_hash
    assert target.execute('SELECT username FROM users WHERE id=2').fetchone()[0] == 'alice-local'
    assert target.execute('SELECT count(*) FROM entries WHERE user_id=1').fetchone()[0] == 1


def test_failed_import_is_atomic_and_changed_source_does_not_overwrite(tmp_path):
    source = database(tmp_path, 'local', 'alice')
    target = database(tmp_path, 'online', 'bob')
    records = read_source(source)
    invalid = copy.deepcopy(records); invalid['ledger'][0]['kind'] = 'invalid'
    with pytest.raises(sqlite3.IntegrityError):
        merge(invalid, target, 'source-1', tmp_path/'before-failure.json')
    assert target.execute('SELECT count(*) FROM users').fetchone()[0] == 1
    assert target.execute('SELECT count(*) FROM local_import_map').fetchone()[0] == 0
    merge(records, target, 'source-1', tmp_path/'before-success.json')
    changed = copy.deepcopy(records); changed['entries'][0]['content'] = 'changed locally'
    with pytest.raises(ValueError, match='refusing to overwrite'):
        merge(changed, target, 'source-1', tmp_path/'before-changed.json')
    assert target.execute('SELECT content FROM entries WHERE id=2').fetchone()[0] == records['entries'][0]['content']
