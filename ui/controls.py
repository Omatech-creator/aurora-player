"""Bottom playback control bar, laid out to match VLC's classic transport toolbar:
seek bar on its own row, then Previous/Play/Stop/Next/Loop/Shuffle on the left and
Playlist/Fullscreen/Volume on the right. Everything else (speed, snapshot, record,
subtitles, filters...) lives in the menu bar, same as stock VLC.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


def format_ms(ms: int) -> str:
    seconds = max(0, ms) // 1000
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class SeekBar(QSlider):
    """Horizontal slider that jumps to the click position (VLC-style) and reports
    hover position for thumbnail-preview support."""

    hovered_ms = Signal(int)
    seeked = Signal(int)  # emitted on click or drag-release with the target ms

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setMouseTracking(True)
        self._pressed = False

    def is_scrubbing(self) -> bool:
        return self._pressed

    def _value_at(self, x: float) -> int:
        ratio = max(0.0, min(1.0, x / max(1, self.width())))
        return int(ratio * self.maximum())

    def mousePressEvent(self, event):
        # Jump directly to the clicked position instead of stepping toward it.
        if event.button() == Qt.LeftButton and self.maximum() > 0:
            self._pressed = True
            value = self._value_at(event.position().x())
            self.setValue(value)
            self.seeked.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.maximum() > 0:
            self.hovered_ms.emit(self._value_at(event.position().x()))
            # While dragging, scrub live.
            if event.buttons() & Qt.LeftButton:
                value = self._value_at(event.position().x())
                self.setValue(value)
                self.seeked.emit(value)


class ControlsBar(QWidget):
    """Self-contained control bar; the main window connects its signals to the engine."""

    play_pause_clicked = Signal()
    stop_clicked = Signal()
    previous_clicked = Signal()
    next_clicked = Signal()
    seek_requested = Signal(int)
    volume_changed = Signal(int)
    mute_toggled = Signal()
    fullscreen_toggled = Signal()
    playlist_toggled = Signal()
    loop_toggled = Signal()
    shuffle_toggled = Signal()
    seek_hover = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlsOverlay")
        self._is_playing = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 8)
        root.setSpacing(4)

        seek_row = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setObjectName("TimeLabel")
        self.seek_bar = SeekBar(self)
        self.seek_bar.seeked.connect(self.seek_requested)
        self.seek_bar.hovered_ms.connect(self.seek_hover)
        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("TimeLabel")
        seek_row.addWidget(self.current_time_label)
        seek_row.addWidget(self.seek_bar, 1)
        seek_row.addWidget(self.duration_label)
        root.addLayout(seek_row)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(6)

        self.previous_btn = self._icon_button("⏮", "Previous")
        self.previous_btn.clicked.connect(self.previous_clicked)
        self.play_btn = self._icon_button("▶", "Play / Pause", object_name="PlayButton")
        self.play_btn.clicked.connect(self.play_pause_clicked)
        self.stop_btn = self._icon_button("⏹", "Stop")
        self.stop_btn.clicked.connect(self.stop_clicked)
        self.next_btn = self._icon_button("⏭", "Next")
        self.next_btn.clicked.connect(self.next_clicked)
        self.loop_btn = self._icon_button("🔁", "Loop (off / one / all)", checkable=True)
        self.loop_btn.clicked.connect(self.loop_toggled)
        self.shuffle_btn = self._icon_button("🔀", "Random", checkable=True)
        self.shuffle_btn.clicked.connect(self.shuffle_toggled)

        for b in (self.previous_btn, self.play_btn, self.stop_btn, self.next_btn, self.loop_btn, self.shuffle_btn):
            buttons_row.addWidget(b)

        buttons_row.addStretch(1)

        self.playlist_btn = self._icon_button("☰", "Toggle Playlist")
        self.playlist_btn.clicked.connect(self.playlist_toggled)
        self.fullscreen_btn = self._icon_button("⛶", "Fullscreen")
        self.fullscreen_btn.clicked.connect(self.fullscreen_toggled)
        buttons_row.addWidget(self.playlist_btn)
        buttons_row.addWidget(self.fullscreen_btn)

        self.mute_btn = self._icon_button("🔊", "Mute")
        self.mute_btn.clicked.connect(self.mute_toggled)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 150)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(self.volume_changed)
        buttons_row.addWidget(self.mute_btn)
        buttons_row.addWidget(self.volume_slider)

        root.addLayout(buttons_row)

        self.setMaximumHeight(76)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade_anim.finished.connect(self._on_fade_finished)

    def _icon_button(
        self, text: str, tooltip: str, checkable: bool = False, object_name: str = "ControlButton"
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    # ---- External state sync -----------------------------------------------------------------
    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        self.play_btn.setText("⏸" if playing else "▶")

    def set_duration(self, duration_ms: int) -> None:
        self.seek_bar.setRange(0, max(1, duration_ms))
        self.duration_label.setText(format_ms(duration_ms))

    def set_position(self, position_ms: int) -> None:
        if not self.seek_bar.is_scrubbing():
            self.seek_bar.setValue(position_ms)
        self.current_time_label.setText(format_ms(position_ms))

    def set_volume_display(self, volume: int, muted: bool) -> None:
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(volume)
        self.volume_slider.blockSignals(False)
        self.mute_btn.setText("🔇" if muted else ("🔊" if volume > 50 else "🔈"))

    def set_loop_icon(self, mode: str) -> None:
        icons = {"off": "🔁", "one": "🔂", "all": "🔁🔁"}
        self.loop_btn.setText(icons.get(mode, "🔁"))
        self.loop_btn.setChecked(mode != "off")

    def fade_in(self) -> None:
        self.show()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self) -> None:
        if self._opacity_effect.opacity() <= 0.01:
            self.hide()
