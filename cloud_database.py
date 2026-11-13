"""SQLite-compatible, transactional Turso HTTP connection (no local replicas)."""
import base64
import re
import sqlite3
from urllib.parse import urlparse

import requests


class Row:
    def __init__(self, names, values):
        self.names, self.values = names, values

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]

    def __iter__(self):
        return iter(self.values)


def encode(value):
    if value is None:
        return {'type': 'null'}
    if isinstance(value, (bool, int)):
        return {'type': 'integer', 'value': str(int(value))}
    if isinstance(value, float):
        return {'type': 'float', 'value': value}
    if isinstance(value, bytes):
        return {'type': 'blob', 'base64': base64.b64encode(value).decode()}
    return {'type': 'text', 'value': str(value)}


def decode(value):
    kind = value['type']
    if kind == 'null':
        return None
    if kind == 'blob':
        return base64.b64decode(value['base64'])
    if kind == 'integer':
        return int(value['value'])
    return value['value']


class Cursor:
    def __init__(self, result=None):
        result = result or {}
        names = [column['name'] for column in result.get('cols', [])]
        self.rows = iter([Row(names, [decode(v) for v in row]) for row in result.get('rows', [])])
        self.rowcount = result.get('affected_row_count', 0)
        self.lastrowid = int(result['last_insert_rowid']) if result.get('last_insert_rowid') else None

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


class Connection:
    def __init__(self, url, token):
        url = url.replace('libsql://', 'https://', 1)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('TURSO_DATABASE_URL must be an HTTPS/libsql database origin')
        if not token:
            raise ValueError('TURSO_AUTH_TOKEN is required')
        self.url = url.rstrip('/') + '/v2/pipeline'
        self.http = requests.Session()
        self.http.headers.update({'Authorization': 'Bearer ' + token})
        self.baton = None
        self.transaction = False
        self.row_factory = None

    def _send(self, operations, close=False):
        operations = operations + ([{'type': 'close'}] if close else [])
        try:
            response = self.http.post(self.url, json={'baton': self.baton, 'requests': operations}, timeout=(10, 30), allow_redirects=False)
            response.raise_for_status()
            payload = response.json()
            self.baton = payload.get('baton')
            if payload.get('base_url'):
                origin = urlparse(payload['base_url'])
                if origin.scheme != 'https' or origin.hostname != urlparse(self.url).hostname:
                    raise ValueError('Unexpected database redirect')
                self.url = payload['base_url'].rstrip('/') + '/v2/pipeline'
            results = []
            for result in payload['results']:
                if result['type'] == 'error':
                    code = result.get('error', {}).get('code', '')
                    if code.startswith('SQLITE_CONSTRAINT'):
                        raise sqlite3.IntegrityError('Database constraint violation')
                    raise sqlite3.OperationalError('Cloud database statement failed')
                results.append(result['response'])
            return results
        except (requests.RequestException, ValueError, KeyError, TypeError):
            self.baton = None
            self.transaction = False
            raise sqlite3.OperationalError('Cloud database connection unavailable') from None

    @staticmethod
    def _statement(sql, args=()):
        return {'type': 'execute', 'stmt': {'sql': sql, 'args': [encode(v) for v in args], 'want_rows': True}}

    def execute(self, sql, args=()):
        if re.match(r'^\s*PRAGMA\s+(journal_mode|foreign_keys)', sql, re.I):
            return Cursor()
        operations = []
        if not self.transaction and re.match(r'^\s*(INSERT|UPDATE|DELETE|REPLACE)\b', sql, re.I):
            operations.append(self._statement('BEGIN IMMEDIATE'))
            self.transaction = True
        operations.append(self._statement(sql, args))
        results = self._send(operations, close=not self.transaction)
        return Cursor(results[len(operations)-1]['result'])

    def executescript(self, script):
        # sqlite3's sequence parser understands statements with quoted semicolons.
        self.commit()
        statement = ''
        for char in script:
            statement += char
            if char == ';' and sqlite3.complete_statement(statement):
                if statement.strip():
                    self.execute(statement)
                statement = ''
        if statement.strip():
            self.execute(statement)
        self.commit()

    def commit(self):
        if self.transaction:
            self._send([self._statement('COMMIT')], close=True)
            self.transaction = False

    def rollback(self):
        if self.transaction:
            try:
                self._send([self._statement('ROLLBACK')], close=True)
            finally:
                self.transaction = False

    def close(self):
        try:
            self.rollback()
        finally:
            self.http.close()
