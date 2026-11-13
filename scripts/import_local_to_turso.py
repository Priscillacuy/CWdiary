"""Explicit, backed-up import. Never run during builds or application startup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud_database import Connection
from account_features import username_key

TABLES = ('users', 'entries', 'ledger', 'analyses', 'password_history')


def digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def private_json(path, value):
    with open(path, 'x', encoding='utf8') as file:
        os.chmod(path, 0o600)
        json.dump(value, file, ensure_ascii=False, indent=2)


def read_source(connection):
    connection.row_factory = sqlite3.Row
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Local database integrity check failed')
    if connection.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Local database contains broken references')
    return {table: [dict(row) for row in connection.execute('SELECT rowid AS __source_rowid,* FROM '+table)] for table in TABLES}


def merge(source, destination, namespace, backup_path):
    """Append only; remap foreign keys and retain all existing online accounts."""
    destination.executescript('''CREATE TABLE IF NOT EXISTS local_import_map(
        source TEXT NOT NULL,table_name TEXT NOT NULL,source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,source_digest TEXT NOT NULL,
        PRIMARY KEY(source,table_name,source_id));
        CREATE TABLE IF NOT EXISTS local_import_runs(
        id TEXT PRIMARY KEY,source TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
    report = {'inserted': {t: 0 for t in TABLES}, 'reused': {t: 0 for t in TABLES}, 'renamed_accounts': [], 'accounts': []}
    try:
        # Acquire a write transaction before allocating IDs or taking the destination backup.
        destination.execute('INSERT INTO local_import_runs(id,source) VALUES(?,?)', (secrets.token_hex(16), namespace))
        original = {t: [dict(r) for r in destination.execute('SELECT * FROM '+t)] for t in TABLES}
        private_json(backup_path, original)
        previous = {(r['table_name'], r['source_id']): dict(r) for r in destination.execute('SELECT * FROM local_import_map WHERE source=?', (namespace,))}
        maxima = destination.execute('SELECT '+','.join('(SELECT COALESCE(MAX('+('rowid' if t=='password_history' else 'id')+'),0) FROM '+t+') AS '+t for t in TABLES)).fetchone()
        next_id = {t: maxima[t] for t in TABLES}
        names = {u['username_key']: u for u in original['users']}
        user_ids, entry_ids, operations = {}, {}, []

        def insert(table, values, ignore=False):
            columns = list(values)
            sql = ('INSERT OR IGNORE' if ignore else 'INSERT')+' INTO '+table+'('+','.join('"'+c+'"' for c in columns)+') VALUES('+','.join('?' for _ in columns)+')'
            operations.append((sql, tuple(values[c] for c in columns)))

        def mapped(table, row):
            key = (table, row['__source_rowid'])
            old = previous.get(key)
            if old and old['source_digest'] != digest(row):
                raise ValueError('Source record changed after an earlier import; refusing to overwrite online edits: '+table)
            return old

        def remember(table, row, target):
            insert('local_import_map', dict(source=namespace, table_name=table, source_id=row['__source_rowid'], target_id=target, source_digest=digest(row)))

        for row in source['users']:
            old = mapped('users', row)
            values = {k: v for k, v in row.items() if k != '__source_rowid'}
            existing = names.get(values['username_key'])
            if old:
                target = old['target_id']; report['reused']['users'] += 1
            elif existing and existing['password_hash'] == values['password_hash']:
                target = existing['id']; remember('users', row, target); report['reused']['users'] += 1
            else:
                if existing:
                    base = values['username']
                    number = 1
                    while True:
                        suffix = '-local'+(str(number) if number > 1 else '')
                        candidate = base[:32-len(suffix)]+suffix
                        if username_key(candidate) not in names:
                            break
                        number += 1
                    values.update(username=candidate, username_key=username_key(candidate))
                    report['renamed_accounts'].append({'from': base, 'to': candidate})
                next_id['users'] += 1; target = next_id['users']; values['id'] = target
                insert('users', values); names[values['username_key']] = values
                remember('users', row, target); report['inserted']['users'] += 1
            user_ids[row['id']] = target
            report['accounts'].append({'local_id': row['id'], 'online_id': target, 'local_username': row['username']})

        for table in TABLES[1:]:
            for row in source[table]:
                old = mapped(table, row)
                if old:
                    target = old['target_id']; report['reused'][table] += 1
                else:
                    values = {k: v for k, v in row.items() if k != '__source_rowid'}
                    values['user_id'] = user_ids[row['user_id']]
                    if table == 'password_history':
                        existing = destination.execute('SELECT rowid FROM password_history WHERE user_id=? AND password_hash=?', (values['user_id'], values['password_hash'])).fetchone()
                        if existing:
                            remember(table, row, existing[0]); report['reused'][table] += 1
                            continue
                    if table == 'analyses' and values.get('entry_id') is not None:
                        values['entry_id'] = entry_ids[values['entry_id']]
                    next_id[table] += 1; target = next_id[table]
                    values['rowid' if table == 'password_history' else 'id'] = target
                    insert(table, values, ignore=table == 'password_history')
                    remember(table, row, target); report['inserted'][table] += 1
                if table == 'entries':
                    entry_ids[row['id']] = target

        # One short HTTP batch rather than holding a write lock across dozens of requests.
        for start in range(0, len(operations), 200):
            batch = operations[start:start+200]
            if hasattr(destination, 'execute_batch'):
                destination.execute_batch(batch)
            else:
                for sql, args in batch:
                    destination.execute(sql, args)
        for table in TABLES:
            count = destination.execute('SELECT COUNT(*) FROM local_import_map WHERE source=? AND table_name=?', (namespace, table)).fetchone()[0]
            if count != len(source[table]):
                raise ValueError('Import count verification failed: '+table)
        destination.commit()
        report['source_counts'] = {t: len(rows) for t, rows in source.items()}
        return report
    except Exception:
        destination.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'instance'/'diary.sqlite3')
    parser.add_argument('--credentials-stdin', action='store_true')
    args = parser.parse_args()
    credentials = json.load(sys.stdin) if args.credentials_stdin else {'url': os.environ['TURSO_DATABASE_URL'], 'token': os.environ['TURSO_AUTH_TOKEN']}
    source_path = args.source.resolve()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)
    backups = source_path.parent/'backups'; backups.mkdir(exist_ok=True, mode=0o700)
    local_backup = backups/('before-cloud-import-'+stamp+'.sqlite3')
    with sqlite3.connect('file:'+str(source_path)+'?mode=ro', uri=True) as local, sqlite3.connect(local_backup) as snapshot:
        os.chmod(local_backup, 0o600); local.backup(snapshot)
    namespace_file = source_path.parent/'.turso-import-namespace'
    if not namespace_file.exists():
        with open(namespace_file, 'x') as file:
            os.chmod(namespace_file, 0o600); file.write(secrets.token_hex(32))
    namespace = namespace_file.read_text().strip()+':'+source_path.name
    with sqlite3.connect(local_backup) as snapshot:
        source = read_source(snapshot)
    remote = Connection(credentials['url'], credentials['token'])
    try:
        report = merge(source, remote, namespace, backups/('cloud-before-import-'+stamp+'.json'))
    finally:
        remote.close()
    report.update(local_backup=str(local_backup), destination='Turso production', completed_at=stamp)
    private_json(backups/('cloud-import-report-'+stamp+'.json'), report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
