"""Subtitle discovery and track/delay management on top of the VLC engine."""

from pathlib import Path

SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


class SubtitleManager:
    """Finds sidecar subtitle files and proxies subtitle settings to the engine."""

    def __init__(self, engine):
        self._engine = engine
        self.delay_ms = 0
        self.current_external: str | None = None

    def find_sidecar_subtitles(self, media_path: str) -> list[str]:
        """Look for subtitle files that share the video's base filename."""
        video_path = Path(media_path)
        if not video_path.exists():
            return []
        found = []
        for sibling in video_path.parent.iterdir():
            if sibling.stem.startswith(video_path.stem) and sibling.suffix.lower() in SUBTITLE_EXTENSIONS:
                found.append(str(sibling))
        return found

    def load_external(self, subtitle_path: str) -> bool:
        ok = self._engine.set_subtitle_file(subtitle_path)
        if ok:
            self.current_external = subtitle_path
        return ok

    def auto_load_for(self, media_path: str) -> str | None:
        """Automatically attach the first matching sidecar subtitle, if any."""
        candidates = self.find_sidecar_subtitles(media_path)
        if candidates:
            self.load_external(candidates[0])
            return candidates[0]
        return None

    def set_delay_ms(self, delay_ms: int) -> None:
        self.delay_ms = delay_ms
        self._engine.set_subtitle_delay(delay_ms)

    def get_tracks(self) -> list[tuple[int, str]]:
        return self._engine.get_subtitle_tracks()

    def set_track(self, track_id: int) -> None:
        self._engine.set_subtitle_track(track_id)

    def disable(self) -> None:
        self._engine.set_subtitle_track(-1)
