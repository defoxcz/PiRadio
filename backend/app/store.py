import json
import sqlite3
from uuid import uuid4


class Store:
    def __init__(self, path):
        # Volání databáze jsou synchronní a serializovaná jedním event loopem.
        # Testovací ASGI klient zakládá aplikaci v jiném vlákně než lifespan.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS stations (id TEXT PRIMARY KEY, name TEXT, url TEXT, image TEXT, favorite INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
        self.db.commit()

    def stations(self):
        return [dict(r) | {'favorite': bool(r['favorite'])} for r in self.db.execute('SELECT * FROM stations ORDER BY rowid')]

    def station(self, id):
        return next((s for s in self.stations() if s['id'] == id), None)

    def save(self, values, id=None):
        id = id or str(uuid4())
        self.db.execute('INSERT OR REPLACE INTO stations VALUES (?, ?, ?, ?, ?)', (id, values.name, values.url, values.image, values.favorite))
        self.db.commit()
        return self.station(id)

    def delete(self, id):
        self.db.execute('DELETE FROM stations WHERE id=?', (id,))
        self.db.commit()

    def get(self, key, default=None):
        r = self.db.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO config VALUES (?, ?)', (key, json.dumps(value)))
        self.db.commit()
