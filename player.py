"""Composition root for the playback subsystem.

Bundles the database connection and all backend managers (settings, history,
playlist, subtitles, VLC engine) into a single object so the UI layer only
needs to construct and wire one thing.
"""
from backend.database import get_database
from backend.settings_manager import SettingsManager
from backend.history_manager import HistoryManager
from backend.playlist_manager import PlaylistManager
from backend.subtitle_manager import SubtitleManager
from backend.vlc_engine import VLCEngine


class PlayerSession:
    """Owns the backend managers for one running instance of the app."""

    def __init__(self):
        self.db = get_database()
        self.settings = SettingsManager(self.db)
        self.history = HistoryManager(self.db)
        self.playlist = PlaylistManager(self.db)
        self.engine = VLCEngine(hw_acceleration=self.settings.get("hw_acceleration"))
        self.subtitles = SubtitleManager(self.engine)

        self.playlist.repeat_mode = self.settings.get("loop_mode")
        self.playlist.shuffle = self.settings.get("shuffle")

    def shutdown(self) -> None:
        self.engine.shutdown()
