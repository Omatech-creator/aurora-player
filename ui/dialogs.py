"""Misc dialogs: open network URL, equalizer, media info, about."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from backend.vlc_engine import EQUALIZER_BANDS


class OpenUrlDialog(QDialog):
    """Open a network stream / HTTP(S) / RTSP / YouTube URL."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Network Stream")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://, rtsp://, or a YouTube URL")
        form.addRow("URL:", self.url_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def url(self) -> str:
        return self.url_edit.text().strip()


class EqualizerDialog(QDialog):
    """10-band graphic equalizer with preamp; emits live values via callback."""

    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equalizer")
        self._on_change = on_change
        self._sliders: list[QSlider] = []

        layout = QVBoxLayout(self)
        self.enable_btn = QPushButton("Enable Equalizer")
        self.enable_btn.setCheckable(True)
        self.enable_btn.toggled.connect(self._emit_change)
        layout.addWidget(self.enable_btn)

        grid = QGridLayout()
        for col, freq in enumerate(EQUALIZER_BANDS):
            slider = QSlider(Qt.Vertical)
            slider.setRange(-20, 20)
            slider.setValue(0)
            slider.valueChanged.connect(self._emit_change)
            grid.addWidget(slider, 0, col, alignment=Qt.AlignHCenter)
            label = QLabel(f"{freq}Hz" if freq < 1000 else f"{freq // 1000}kHz")
            grid.addWidget(label, 1, col, alignment=Qt.AlignHCenter)
            self._sliders.append(slider)
        layout.addLayout(grid)

        preamp_row = QHBoxLayout()
        preamp_row.addWidget(QLabel("Preamp"))
        self.preamp_slider = QSlider(Qt.Horizontal)
        self.preamp_slider.setRange(-20, 20)
        self.preamp_slider.valueChanged.connect(self._emit_change)
        preamp_row.addWidget(self.preamp_slider)
        layout.addLayout(preamp_row)

    def _emit_change(self) -> None:
        if self._on_change:
            gains = [s.value() for s in self._sliders]
            self._on_change(self.enable_btn.isChecked(), gains, self.preamp_slider.value())


class MediaInfoDialog(QDialog):
    """Read-only codec/stats panel for the currently playing file."""

    def __init__(self, info_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Media Information")
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(info_text)
        layout.addWidget(text)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        layout = QVBoxLayout(self)
        label = QLabel(
            "<h2>Aurora Player</h2>"
            "<p>A modern, fast, lightweight media player built with PySide6 and libVLC.</p>"
            "<p>Inspired by VLC, KMPlayer, PotPlayer and MPC-HC.</p>"
        )
        label.setTextFormat(Qt.RichText)
        layout.addWidget(label)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
