import json
from datetime import datetime, timezone
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
        self.db.execute('CREATE TABLE IF NOT EXISTS play_history (id INTEGER PRIMARY KEY, station_id TEXT, name TEXT, url TEXT, image TEXT, started_at TEXT, demo INTEGER NOT NULL)')
        for table in ('stations', 'play_history'):
            if 'live' not in {row[1] for row in self.db.execute(f'PRAGMA table_info({table})')}:
                self.db.execute(f'ALTER TABLE {table} ADD COLUMN live INTEGER NOT NULL DEFAULT 1')
        self.db.commit()

    def stations(self):
        return [dict(r) | {'favorite': bool(r['favorite']), 'live': bool(r['live'])} for r in self.db.execute('SELECT * FROM stations ORDER BY rowid')]

    def station(self, id):
        return next((s for s in self.stations() if s['id'] == id), None)

    def save(self, values, id=None):
        id = id or str(uuid4())
        self.db.execute('INSERT OR REPLACE INTO stations(id,name,url,image,favorite,live) VALUES (?, ?, ?, ?, ?, ?)', (id, values.name, values.url, values.image, values.favorite, values.live))
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


    def record_play(self, station, demo):
        with self.db:
            self.db.execute('INSERT INTO play_history(station_id,name,url,image,started_at,demo,live) VALUES (?,?,?,?,?,?,?)',
                            (station['id'], station['name'], station['url'], station.get('image', ''), datetime.now(timezone.utc).isoformat(), int(demo), int(station.get('live', True))))
            self.db.execute('DELETE FROM play_history WHERE id NOT IN (SELECT id FROM play_history ORDER BY id DESC LIMIT 500)')

    def history(self):
        return [dict(row) | {'demo': bool(row['demo'])} for row in self.db.execute('SELECT * FROM play_history ORDER BY id DESC LIMIT 100')]

    def history_entry(self, id):
        row = self.db.execute('SELECT * FROM play_history WHERE id=?', (id,)).fetchone()
        return dict(row) if row else None
