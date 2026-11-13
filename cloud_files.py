"""Private durable cache and expiring worker leases in the application's Turso DB."""
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from cloud_database import Connection


class FileStore:
    def __init__(self, root, url, token):
        self.root, self.url, self.token = Path(root), url, token
        db = self.connection()
        try:
            db.executescript('''CREATE TABLE IF NOT EXISTS cloud_files(path TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS cloud_leases(path TEXT PRIMARY KEY, owner TEXT NOT NULL, until_at REAL NOT NULL);''')
        finally:
            db.close()

    def connection(self):
        return Connection(self.url, self.token)

    def key(self, path):
        return str(Path(path).resolve().relative_to(self.root.resolve()))

    def load(self, path, refresh=False):
        path = Path(path)
        if path.is_file() and not refresh:
            return path
        db = self.connection()
        try:
            row = db.execute('SELECT content FROM cloud_files WHERE path=?', (self.key(path),)).fetchone()
        finally:
            db.close()
        if row:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + '.' + secrets.token_hex(6) + '.download')
            temporary.write_bytes(row[0]); temporary.replace(path)
        return path

    def upload(self, path):
        db = self.connection()
        try:
            db.execute('INSERT OR REPLACE INTO cloud_files(path,content) VALUES(?,?)', (self.key(path), Path(path).read_bytes()))
            db.commit()
        finally:
            db.close()

    def delete(self, path):
        db = self.connection()
        try:
            db.execute('DELETE FROM cloud_files WHERE path=?', (self.key(path),)); db.commit()
        finally:
            db.close()

    @contextmanager
    def lease(self, path):
        key, owner, now = self.key(path), secrets.token_hex(16), time.time()
        db = self.connection()
        try:
            db.execute('INSERT OR IGNORE INTO cloud_leases(path,owner,until_at) VALUES(?,?,0)', (key, owner))
            changed = db.execute('UPDATE cloud_leases SET owner=?,until_at=? WHERE path=? AND until_at<?', (owner, now+290, key, now))
            acquired = bool(changed.rowcount); db.commit()
        finally:
            db.close()
        try:
            yield acquired
        finally:
            if acquired:
                db = self.connection()
                try:
                    db.execute('DELETE FROM cloud_leases WHERE path=? AND owner=?', (key, owner)); db.commit()
                finally:
                    db.close()
