"""Tracks recently played media, resume positions, favorites and bookmarks."""

from datetime import datetime, timezone

from backend.database import Database, get_database


class HistoryManager:
    def __init__(self, db: Database | None = None):
        self._db = db or get_database()

    # ---- Playback history / resume -------------------------------------------------
    def record_play(self, path: str, title: str, duration_ms: int = 0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._db.fetchone("SELECT id, play_count FROM history WHERE path = ?", (path,))
        if existing:
            self._db.execute(
                "UPDATE history SET title=?, last_played=?, play_count=play_count+1, duration_ms=? WHERE path=?",
                (title, now, duration_ms, path),
            )
        else:
            self._db.execute(
                "INSERT INTO history (path, title, position_ms, duration_ms, last_played, play_count) "
                "VALUES (?, ?, 0, ?, ?, 1)",
                (path, title, duration_ms, now),
            )

    def update_position(self, path: str, position_ms: int) -> None:
        self._db.execute("UPDATE history SET position_ms = ? WHERE path = ?", (position_ms, path))

    def get_resume_position(self, path: str) -> int:
        row = self._db.fetchone("SELECT position_ms FROM history WHERE path = ?", (path,))
        return row["position_ms"] if row else 0

    def get_recent(self, limit: int = 50):
        return self._db.fetchall("SELECT * FROM history ORDER BY last_played DESC LIMIT ?", (limit,))

    def clear_history(self) -> None:
        self._db.execute("DELETE FROM history")

    # ---- Favorites -------------------------------------------------------------------
    def add_favorite(self, path: str, title: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT OR IGNORE INTO favorites (path, title, added_on) VALUES (?, ?, ?)",
            (path, title, now),
        )

    def remove_favorite(self, path: str) -> None:
        self._db.execute("DELETE FROM favorites WHERE path = ?", (path,))

    def is_favorite(self, path: str) -> bool:
        return self._db.fetchone("SELECT 1 FROM favorites WHERE path = ?", (path,)) is not None

    def get_favorites(self):
        return self._db.fetchall("SELECT * FROM favorites ORDER BY added_on DESC")

    # ---- Bookmarks ---------------------------------------------------------------------
    def add_bookmark(self, path: str, label: str, position_ms: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO bookmarks (path, label, position_ms, created_on) VALUES (?, ?, ?, ?)",
            (path, label, position_ms, now),
        )

    def get_bookmarks(self, path: str):
        return self._db.fetchall("SELECT * FROM bookmarks WHERE path = ? ORDER BY position_ms ASC", (path,))

    def remove_bookmark(self, bookmark_id: int) -> None:
        self._db.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
