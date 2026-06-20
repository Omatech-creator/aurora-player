"""Tabbed settings/preferences dialog backed by SettingsManager."""

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend.settings_manager import SettingsManager


class SettingsDialog(QDialog):
    """Reads current values from SettingsManager and writes back on Save."""

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumSize(560, 480)
        self._settings = settings

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_general_tab()
        self._build_playback_tab()
        self._build_audio_tab()
        self._build_video_tab()
        self._build_subtitles_tab()
        self._build_shortcuts_tab()
        self._build_theme_tab()
        self._build_performance_tab()
        self._build_network_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._on_restore_defaults)
        layout.addWidget(buttons)

    def _add_tab(self, title: str) -> QFormLayout:
        page = QWidget()
        form = QFormLayout(page)
        self.tabs.addTab(page, title)
        return form

    def _build_general_tab(self) -> None:
        form = self._add_tab("General")
        self.resume_checkbox = QCheckBox("Resume playback from last position")
        self.resume_checkbox.setChecked(self._settings.get("resume_playback"))
        form.addRow(self.resume_checkbox)
        self.auto_update_checkbox = QCheckBox("Check for updates automatically")
        self.auto_update_checkbox.setChecked(self._settings.get("auto_update_check"))
        form.addRow(self.auto_update_checkbox)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Español", "Français", "Deutsch", "日本語"])
        form.addRow("Language:", self.language_combo)

    def _build_playback_tab(self) -> None:
        form = self._add_tab("Playback")
        self.loop_combo = QComboBox()
        self.loop_combo.addItems(["off", "one", "all"])
        self.loop_combo.setCurrentText(self._settings.get("loop_mode"))
        form.addRow("Default loop mode:", self.loop_combo)
        self.shuffle_checkbox = QCheckBox("Shuffle by default")
        self.shuffle_checkbox.setChecked(self._settings.get("shuffle"))
        form.addRow(self.shuffle_checkbox)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(25, 300)
        self.speed_spin.setSuffix(" %")
        self.speed_spin.setValue(int(self._settings.get("playback_speed") * 100))
        form.addRow("Default playback speed:", self.speed_spin)

    def _build_audio_tab(self) -> None:
        form = self._add_tab("Audio")
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(0, 150)
        self.volume_spin.setValue(self._settings.get("volume"))
        form.addRow("Default volume:", self.volume_spin)
        self.audio_delay_spin = QSpinBox()
        self.audio_delay_spin.setRange(-5000, 5000)
        self.audio_delay_spin.setSuffix(" ms")
        self.audio_delay_spin.setValue(self._settings.get("audio_delay_ms"))
        form.addRow("Audio delay:", self.audio_delay_spin)
        self.remember_audio_checkbox = QCheckBox("Remember audio track per file")
        self.remember_audio_checkbox.setChecked(self._settings.get("remember_audio_track"))
        form.addRow(self.remember_audio_checkbox)

    def _build_video_tab(self) -> None:
        form = self._add_tab("Video")
        self.hw_accel_checkbox = QCheckBox("Hardware acceleration")
        self.hw_accel_checkbox.setChecked(self._settings.get("hw_acceleration"))
        form.addRow(self.hw_accel_checkbox)
        form.addRow(
            QLabel("4K/8K playback and HDR pass-through follow the source\nand depend on GPU/driver decoder support.")
        )

    def _build_subtitles_tab(self) -> None:
        form = self._add_tab("Subtitles")
        self.subtitle_delay_spin = QSpinBox()
        self.subtitle_delay_spin.setRange(-5000, 5000)
        self.subtitle_delay_spin.setSuffix(" ms")
        self.subtitle_delay_spin.setValue(self._settings.get("subtitle_delay_ms"))
        form.addRow("Subtitle delay:", self.subtitle_delay_spin)
        self.remember_subtitle_checkbox = QCheckBox("Remember subtitle selection per file")
        self.remember_subtitle_checkbox.setChecked(self._settings.get("remember_subtitle"))
        form.addRow(self.remember_subtitle_checkbox)

    def _build_shortcuts_tab(self) -> None:
        form = self._add_tab("Keyboard Shortcuts")
        self._shortcut_edits: dict[str, QLineEdit] = {}
        for action, keys in self._settings.get("shortcuts").items():
            edit = QLineEdit(keys)
            form.addRow(action.replace("_", " ").title() + ":", edit)
            self._shortcut_edits[action] = edit

    def _build_theme_tab(self) -> None:
        form = self._add_tab("Theme")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self._settings.get("theme"))
        form.addRow("Theme:", self.theme_combo)
        self.accent_btn = QPushButton(self._settings.get("accent_color"))
        self.accent_btn.clicked.connect(self._pick_accent_color)
        form.addRow("Accent color:", self.accent_btn)

    def _build_performance_tab(self) -> None:
        form = self._add_tab("Performance")
        self.cache_spin = QSpinBox()
        self.cache_spin.setRange(32, 2048)
        self.cache_spin.setSuffix(" MB")
        self.cache_spin.setValue(self._settings.get("cache_size_mb"))
        form.addRow("Cache size:", self.cache_spin)

    def _build_network_tab(self) -> None:
        form = self._add_tab("Network")
        form.addRow(
            QLabel(
                "Network caching, proxy and DLNA/Chromecast discovery\nsettings will appear here as those integrations are added."
            )
        )

    def _pick_accent_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.accent_btn.setText(color.name())

    def _on_save(self) -> None:
        self._settings.set("resume_playback", self.resume_checkbox.isChecked())
        self._settings.set("auto_update_check", self.auto_update_checkbox.isChecked())
        self._settings.set("loop_mode", self.loop_combo.currentText())
        self._settings.set("shuffle", self.shuffle_checkbox.isChecked())
        self._settings.set("playback_speed", self.speed_spin.value() / 100)
        self._settings.set("volume", self.volume_spin.value())
        self._settings.set("audio_delay_ms", self.audio_delay_spin.value())
        self._settings.set("remember_audio_track", self.remember_audio_checkbox.isChecked())
        self._settings.set("hw_acceleration", self.hw_accel_checkbox.isChecked())
        self._settings.set("subtitle_delay_ms", self.subtitle_delay_spin.value())
        self._settings.set("remember_subtitle", self.remember_subtitle_checkbox.isChecked())
        self._settings.set("theme", self.theme_combo.currentText())
        self._settings.set("accent_color", self.accent_btn.text())
        self._settings.set("cache_size_mb", self.cache_spin.value())
        shortcuts = {action: edit.text() for action, edit in self._shortcut_edits.items()}
        self._settings.set("shortcuts", shortcuts)
        self.accept()

    def _on_restore_defaults(self) -> None:
        self._settings.reset_to_defaults()
        self.reject()
