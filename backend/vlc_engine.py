"""Thin Qt-friendly wrapper around libVLC (python-vlc) that exposes playback,
audio/video adjustment, subtitle, equalizer and snapshot/record primitives.

All libVLC calls are funnelled through this class so the rest of the app never
touches the vlc module directly (keeps UI/backend separated, MVC-style).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import vlc
from PySide6.QtCore import QObject, QTimer, Signal

ADJUST_OPTIONS = {
    "contrast": vlc.VideoAdjustOption.Contrast,
    "brightness": vlc.VideoAdjustOption.Brightness,
    "hue": vlc.VideoAdjustOption.Hue,
    "saturation": vlc.VideoAdjustOption.Saturation,
    "gamma": vlc.VideoAdjustOption.Gamma,
}

EQUALIZER_BANDS = (60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000)


class VLCEngine(QObject):
    """Wraps a libvlc.Instance + MediaPlayer pair and polls state on a QTimer."""

    position_changed = Signal(int, int)     # current_ms, duration_ms
    state_changed = Signal(str)             # playing | paused | stopped | ended | error
    media_changed = Signal(str)             # path of newly loaded media
    error_occurred = Signal(str)

    def __init__(self, hw_acceleration: bool = True, parent=None):
        super().__init__(parent)
        args = ["--no-video-title-show", "--quiet"]
        if hw_acceleration:
            args.append("--avcodec-hw=any")
        self._instance = vlc.Instance(args)
        self._player: vlc.MediaPlayer = self._instance.media_player_new()
        self._equalizer: vlc.AudioEqualizer | None = None
        self._current_path: str | None = None
        self._was_playing_before_seek_drag = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)
        self._poll_timer.timeout.connect(self._poll_state)
        self._poll_timer.start()
        self._last_state = None

    # ---- Window embedding -----------------------------------------------------------------
    def attach_to_widget(self, win_id: int, platform: str = "win32") -> None:
        if platform == "win32":
            self._player.set_hwnd(win_id)
        elif platform == "darwin":
            self._player.set_nsobject(win_id)
        else:
            self._player.set_xwindow(win_id)

    # ---- Media loading ----------------------------------------------------------------------
    def load(self, path: str, start_ms: int = 0) -> None:
        media = self._instance.media_new(path)
        self._player.set_media(media)
        self._current_path = path
        self.media_changed.emit(path)
        self._player.play()
        if start_ms > 0:
            QTimer.singleShot(300, lambda: self.seek_ms(start_ms))

    def current_path(self) -> str | None:
        return self._current_path

    # ---- Transport controls -----------------------------------------------------------------
    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play_pause(self) -> None:
        if self._player.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()

    def is_playing(self) -> bool:
        return bool(self._player.is_playing())

    # ---- Seeking / time -----------------------------------------------------------------------
    def seek_ms(self, position_ms: int) -> None:
        self._player.set_time(max(0, int(position_ms)))

    def seek_relative(self, delta_ms: int) -> None:
        new_pos = max(0, self._player.get_time() + delta_ms)
        self._player.set_time(new_pos)

    def get_time_ms(self) -> int:
        return max(0, self._player.get_time())

    def get_duration_ms(self) -> int:
        return max(0, self._player.get_length())

    def next_frame(self) -> None:
        """Frame-by-frame stepping; only effective while paused."""
        self._player.next_frame()

    # ---- Volume / mute --------------------------------------------------------------------------
    def set_volume(self, volume_percent: int) -> None:
        self._player.audio_set_volume(max(0, min(200, volume_percent)))

    def get_volume(self) -> int:
        return self._player.audio_get_volume()

    def set_muted(self, muted: bool) -> None:
        self._player.audio_set_mute(muted)

    def is_muted(self) -> bool:
        return bool(self._player.audio_get_mute())

    # ---- Playback speed -------------------------------------------------------------------------
    def set_rate(self, rate: float) -> None:
        self._player.set_rate(rate)

    def get_rate(self) -> float:
        return self._player.get_rate()

    # ---- Audio / subtitle delay -----------------------------------------------------------------
    def set_audio_delay(self, delay_ms: int) -> None:
        self._player.audio_set_delay(delay_ms * 1000)

    def set_subtitle_delay(self, delay_ms: int) -> None:
        self._player.video_set_spu_delay(delay_ms * 1000)

    # ---- Subtitles -------------------------------------------------------------------------------
    def set_subtitle_file(self, subtitle_path: str) -> bool:
        try:
            return self._player.add_slave(vlc.MediaSlaveType.subtitle, Path(subtitle_path).as_uri(), True) == 0
        except Exception:
            return False

    def get_subtitle_tracks(self) -> list[tuple[int, str]]:
        descriptions = self._player.video_get_spu_description() or []
        return [(track_id, label.decode("utf-8", "ignore") if isinstance(label, bytes) else label)
                for track_id, label in descriptions]

    def set_subtitle_track(self, track_id: int) -> None:
        self._player.video_set_spu(track_id)

    # ---- Audio tracks -----------------------------------------------------------------------------
    def get_audio_tracks(self) -> list[tuple[int, str]]:
        descriptions = self._player.audio_get_track_description() or []
        return [(track_id, label.decode("utf-8", "ignore") if isinstance(label, bytes) else label)
                for track_id, label in descriptions]

    def set_audio_track(self, track_id: int) -> None:
        self._player.audio_set_track(track_id)

    # ---- Video geometry: aspect ratio / crop / zoom / rotate / mirror -----------------------------
    def set_aspect_ratio(self, ratio: str | None) -> None:
        """ratio examples: '16:9', '4:3', '1:1', or None to restore source aspect."""
        self._player.video_set_aspect_ratio(ratio)

    def set_crop(self, geometry: str | None) -> None:
        """geometry examples: '16:9', '4:3', '1.85:1', or None to disable cropping."""
        self._player.video_set_crop_geometry(geometry)

    def set_zoom(self, scale: float) -> None:
        self._player.video_set_scale(scale)

    def set_rotation(self, degrees: int) -> None:
        """Applies a rotate filter. Re-attaches on the running media (best-effort)."""
        media = self._player.get_media()
        if media is None:
            return
        media.add_option(f":video-filter=rotate")
        media.add_option(f":rotate-angle={degrees}")

    def set_mirror(self, enabled: bool) -> None:
        media = self._player.get_media()
        if media is None:
            return
        if enabled:
            media.add_option(":video-filter=transform")
            media.add_option(":transform-type=hflip")
        else:
            media.add_option(":video-filter=")

    # ---- Color adjustments: brightness / contrast / gamma / hue / saturation ----------------------
    def set_adjust_enabled(self, enabled: bool) -> None:
        self._player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 1 if enabled else 0)

    def set_adjustment(self, name: str, value: float) -> None:
        option = ADJUST_OPTIONS.get(name)
        if option is None:
            return
        self.set_adjust_enabled(True)
        self._player.video_set_adjust_float(option, value)

    # ---- Equalizer -----------------------------------------------------------------------------------
    def enable_equalizer(self, band_gains: list[float] | None = None, preamp: float = 0.0) -> None:
        self._equalizer = vlc.AudioEqualizer()
        if band_gains:
            for index, gain in enumerate(band_gains[: len(EQUALIZER_BANDS)]):
                self._equalizer.set_amp_at_index(gain, index)
        self._equalizer.set_preamp(preamp)
        self._player.set_equalizer(self._equalizer)

    def disable_equalizer(self) -> None:
        self._equalizer = None
        self._player.set_equalizer(None)

    # ---- Snapshot / clip recording ----------------------------------------------------------------
    def take_snapshot(self, output_path: str, width: int = 0, height: int = 0) -> bool:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return self._player.video_take_snapshot(0, output_path, width, height) == 0

    def record_clip(self, source_path: str, output_path: str, start_ms: int, end_ms: int) -> bool:
        """Extracts [start_ms, end_ms) from a local media file using ffmpeg (re-encode-free trim)."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        start_s = start_ms / 1000
        duration_s = max(0.1, (end_ms - start_ms) / 1000)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", str(start_s), "-i", source_path,
                    "-t", str(duration_s), "-c", "copy", output_path,
                ],
                check=True, capture_output=True,
            )
            return True
        except Exception as exc:
            self.error_occurred.emit(f"Clip recording failed: {exc}")
            return False

    # ---- State polling --------------------------------------------------------------------------------
    def _poll_state(self) -> None:
        state = self._player.get_state()
        mapped = {
            vlc.State.Playing: "playing",
            vlc.State.Paused: "paused",
            vlc.State.Stopped: "stopped",
            vlc.State.Ended: "ended",
            vlc.State.Error: "error",
        }.get(state)
        if mapped and mapped != self._last_state:
            self._last_state = mapped
            self.state_changed.emit(mapped)
            if mapped == "error":
                self.error_occurred.emit(f"Playback error for {self._current_path}")
        if state in (vlc.State.Playing, vlc.State.Paused):
            self.position_changed.emit(self.get_time_ms(), self.get_duration_ms())

    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._player.stop()
        self._player.release()
        self._instance.release()
