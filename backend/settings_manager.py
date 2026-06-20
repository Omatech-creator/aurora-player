"""Persists application settings (window state, playback prefs, shortcuts) to SQLite."""
import json
from typing import Any

from backend.database import Database, get_database

DEFAULTS: dict[str, Any] = {
    "window_width": 1280,
    "window_height": 800,
    "window_maximized": False,
    "volume": 80,
    "muted": False,
    "playback_speed": 1.0,
    "loop_mode": "off",       # off | one | all
    "shuffle": False,
    "hw_acceleration": True,
    "resume_playback": True,
    "remember_subtitle": True,
    "remember_audio_track": True,
    "subtitle_delay_ms": 0,
    "audio_delay_ms": 0,
    "theme": "dark",
    "accent_color": "#3D8BFD",
    "library_folders": [],
    "cache_size_mb": 256,
    "sleep_timer_minutes": 0,
    "always_on_top": False,
    "auto_update_check": True,
    "shortcuts": {
        "play_pause": "Space",
        "backward": "Left",
        "forward": "Right",
        "volume_up": "Up",
        "volume_down": "Down",
        "fullscreen": "F",
        "exit_fullscreen": "Esc",
        "mute": "M",
        "open_file": "Ctrl+O",
        "open_folder": "Ctrl+Shift+O",
        "preferences": "Ctrl+P",
        "playlist": "Ctrl+L",
        "history": "Ctrl+H",
        "quit": "Ctrl+Q",
    },
}


class SettingsManager:
    """Simple typed key/value settings store backed by SQLite."""

    def __init__(self, db: Database | None = None):
        self._db = db or get_database()
        self._cache: dict[str, Any] = {}
        self._load_all()

    def _load_all(self):
        rows = self._db.fetchall("SELECT key, value FROM settings")
        stored = {row["key"]: json.loads(row["value"]) for row in rows}
        self._cache = {**DEFAULTS, **stored}

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    def all(self) -> dict[str, Any]:
        return dict(self._cache)

    def reset_to_defaults(self) -> None:
        for key, value in DEFAULTS.items():
            self.set(key, value)
