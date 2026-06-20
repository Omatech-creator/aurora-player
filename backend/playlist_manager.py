"""Manages the active playlist (queue) plus persistence of named playlists to SQLite."""

import random
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from backend.database import Database, get_database

REPEAT_OFF, REPEAT_ONE, REPEAT_ALL = "off", "one", "all"


class PlaylistManager(QObject):
    """Holds the in-memory playback queue and emits signals on changes."""

    items_changed = Signal()
    current_index_changed = Signal(int)

    def __init__(self, db: Database | None = None):
        super().__init__()
        self._db = db or get_database()
        self._items: list[str] = []
        self._order: list[int] = []  # shuffled index order, identity when shuffle is off
        self._current_pos = -1  # position within self._order
        self.repeat_mode = REPEAT_OFF
        self.shuffle = False

    # ---- Queue management --------------------------------------------------------------
    @property
    def items(self) -> list[str]:
        return list(self._items)

    def current_path(self) -> str | None:
        if 0 <= self._current_pos < len(self._order):
            return self._items[self._order[self._current_pos]]
        return None

    def current_index(self) -> int:
        if 0 <= self._current_pos < len(self._order):
            return self._order[self._current_pos]
        return -1

    def add(self, path: str) -> None:
        self._items.append(path)
        self._rebuild_order(keep_current=True)
        self.items_changed.emit()

    def add_many(self, paths: list[str]) -> None:
        self._items.extend(paths)
        self._rebuild_order(keep_current=True)
        self.items_changed.emit()

    def remove_at(self, index: int) -> None:
        if 0 <= index < len(self._items):
            current_path = self.current_path()
            del self._items[index]
            self._rebuild_order(keep_current=False)
            if current_path and current_path in self._items:
                self._current_pos = self._order.index(self._items.index(current_path))
            self.items_changed.emit()

    def clear(self) -> None:
        self._items.clear()
        self._order.clear()
        self._current_pos = -1
        self.items_changed.emit()

    def move(self, from_index: int, to_index: int) -> None:
        """Reorder via drag and drop in the playlist widget."""
        if from_index == to_index or not (0 <= from_index < len(self._items)):
            return
        item = self._items.pop(from_index)
        self._items.insert(to_index, item)
        self._rebuild_order(keep_current=True)
        self.items_changed.emit()

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._current_pos = self._order.index(index)
            self.current_index_changed.emit(index)

    def set_shuffle(self, enabled: bool) -> None:
        self.shuffle = enabled
        self._rebuild_order(keep_current=True)

    def set_repeat(self, mode: str) -> None:
        self.repeat_mode = mode

    def _rebuild_order(self, keep_current: bool) -> None:
        current_path = self.current_path() if keep_current else None
        self._order = list(range(len(self._items)))
        if self.shuffle:
            random.shuffle(self._order)
        if current_path and current_path in self._items:
            real_idx = self._items.index(current_path)
            self._current_pos = self._order.index(real_idx)
        elif self._items:
            self._current_pos = min(max(self._current_pos, 0), len(self._order) - 1)
        else:
            self._current_pos = -1

    def next(self) -> str | None:
        if not self._order:
            return None
        if self.repeat_mode == REPEAT_ONE:
            return self.current_path()
        if self._current_pos + 1 < len(self._order):
            self._current_pos += 1
        elif self.repeat_mode == REPEAT_ALL:
            self._current_pos = 0
        else:
            return None
        self.current_index_changed.emit(self.current_index())
        return self.current_path()

    def previous(self) -> str | None:
        if not self._order:
            return None
        if self._current_pos - 1 >= 0:
            self._current_pos -= 1
        elif self.repeat_mode == REPEAT_ALL:
            self._current_pos = len(self._order) - 1
        else:
            return None
        self.current_index_changed.emit(self.current_index())
        return self.current_path()

    # ---- Persistence (save/load named playlists) ----------------------------------------
    def save_playlist(self, name: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO playlists (name, created_on) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET created_on = excluded.created_on",
            (name, now),
        )
        row = self._db.fetchone("SELECT id FROM playlists WHERE name = ?", (name,))
        playlist_id = row["id"]
        self._db.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
        for position, path in enumerate(self._items):
            self._db.execute(
                "INSERT INTO playlist_items (playlist_id, path, position) VALUES (?, ?, ?)",
                (playlist_id, path, position),
            )

    def load_playlist(self, name: str) -> bool:
        row = self._db.fetchone("SELECT id FROM playlists WHERE name = ?", (name,))
        if not row:
            return False
        rows = self._db.fetchall(
            "SELECT path FROM playlist_items WHERE playlist_id = ? ORDER BY position ASC",
            (row["id"],),
        )
        self._items = [r["path"] for r in rows]
        self._rebuild_order(keep_current=False)
        self._current_pos = 0 if self._items else -1
        self.items_changed.emit()
        return True

    def list_saved_playlists(self) -> list[str]:
        rows = self._db.fetchall("SELECT name FROM playlists ORDER BY created_on DESC")
        return [r["name"] for r in rows]

    def export_to_m3u(self, file_path: str) -> None:
        path = Path(file_path)
        with path.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in self._items:
                f.write(item + "\n")

    def import_from_m3u(self, file_path: str) -> None:
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as f:
            paths = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        self.add_many(paths)
