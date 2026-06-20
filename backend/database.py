"""SQLite database layer for settings, history, favorites, playlists and bookmarks."""

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "player.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    position_ms INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    last_played TEXT,
    play_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    added_on TEXT
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_on TEXT
);

CREATE TABLE IF NOT EXISTS playlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    position INTEGER NOT NULL,
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    label TEXT,
    position_ms INTEGER NOT NULL,
    created_on TEXT
);

CREATE TABLE IF NOT EXISTS library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    duration_ms INTEGER DEFAULT 0,
    resolution TEXT,
    codec TEXT,
    thumbnail_path TEXT,
    category TEXT,
    added_on TEXT
);
"""


class Database:
    """Thread-safe SQLite wrapper used by the manager classes."""

    _lock = threading.Lock()

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(query, params)
            self._conn.commit()
            return cur

    def fetchall(self, query: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(query, params)
            return cur.fetchall()

    def fetchone(self, query: str, params: tuple = ()):
        with self._lock:
            cur = self._conn.execute(query, params)
            return cur.fetchone()

    def close(self):
        self._conn.close()


_instance: Database | None = None


def get_database() -> Database:
    """Return the process-wide singleton database connection."""
    global _instance
    if _instance is None:
        _instance = Database()
    return _instance
