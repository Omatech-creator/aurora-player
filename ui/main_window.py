"""Top-level application window, styled after VLC's classic interface: a standard
OS window, a full menu bar (Media/Playback/Audio/Video/Subtitle/Tools/View/Help), a
persistent video canvas with a transport bar below it, and a togglable side panel
for the playlist/library/history/favorites. Wires UI signals to the backend managers
(engine, playlist, history, subtitles, settings) — this module is the "controller" in
the MVC split; backend/ holds the model, ui/* holds the views.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend.playlist_manager import REPEAT_ALL, REPEAT_OFF, REPEAT_ONE
from player import PlayerSession
from ui.controls import ControlsBar
from ui.dialogs import AboutDialog, EqualizerDialog, MediaInfoDialog, OpenUrlDialog
from ui.playlist import PlaylistPanel
from ui.settings import SettingsDialog

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".mpeg", ".mpg", ".3gp", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".aac", ".wav", ".flac", ".ogg", ".m4a"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icons" / "app_icon.ico"


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS


class MediaListPage(QWidget):
    """Reusable list view for the Library / History / Favorites tabs."""

    def __init__(self, title: str, show_search: bool = True, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        if show_search:
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Search...")
            self.search_edit.textChanged.connect(self._filter)
            layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(48, 27))
        layout.addWidget(self.list_widget, 1)

    def _filter(self, text: str) -> None:
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def populate(self, entries: list[tuple[str, str]]) -> None:
        """entries: list of (display_text, full_path)."""
        self.list_widget.clear()
        for display_text, path in entries:
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, path)
            self.list_widget.addItem(item)


class VideoCanvas(QWidget):
    """Black surface that libVLC renders into via its native window handle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoCanvas")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aurora Player")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.session = PlayerSession()
        self.settings = self.session.settings
        self.history = self.session.history
        self.playlist = self.session.playlist
        self.engine = self.session.engine
        self.subtitles = self.session.subtitles

        self._is_fullscreen = False
        self._is_recording = False
        self._record_start_ms = 0
        self._hide_controls_timer = QTimer(self)
        self._hide_controls_timer.setInterval(3000)
        self._hide_controls_timer.timeout.connect(self._auto_hide_controls)
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_timer)
        self._pip_window: QWidget | None = None

        self._build_ui()
        self._build_menu_bar()
        self._wire_signals()
        self._restore_window_state()
        self._refresh_browse_pages()

    # ---- UI construction -------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.video_splitter = QSplitter(Qt.Horizontal)
        video_container = QWidget()
        video_v = QVBoxLayout(video_container)
        video_v.setContentsMargins(0, 0, 0, 0)
        self.video_canvas = VideoCanvas()
        video_v.addWidget(self.video_canvas, 1)
        self.controls_bar = ControlsBar()
        video_v.addWidget(self.controls_bar)
        self.video_splitter.addWidget(video_container)

        self.side_tabs = QTabWidget()
        self.playlist_panel = PlaylistPanel()
        self.side_tabs.addTab(self.playlist_panel, "Playlist")
        self.library_videos_page = MediaListPage("Videos")
        self.library_music_page = MediaListPage("Music")
        self.library_tabs = QTabWidget()
        self.library_tabs.addTab(self.library_videos_page, "Videos")
        self.library_tabs.addTab(self.library_music_page, "Music")
        self.side_tabs.addTab(self.library_tabs, "Media Library")
        self.history_page = MediaListPage("History")
        self.side_tabs.addTab(self.history_page, "History")
        self.favorites_page = MediaListPage("Favorites", show_search=False)
        self.side_tabs.addTab(self.favorites_page, "Favorites")

        for page in (self.library_videos_page, self.library_music_page, self.history_page, self.favorites_page):
            page.list_widget.itemDoubleClicked.connect(lambda item: self._play_path(item.data(Qt.UserRole)))

        self.video_splitter.addWidget(self.side_tabs)
        self.video_splitter.setSizes([1000, 320])
        self.side_tabs.hide()

        outer.addWidget(self.video_splitter, 1)

        self.now_playing_label = QLabel("No media loaded")
        self.statusBar().addWidget(self.now_playing_label)

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        media_menu = menu_bar.addMenu("&Media")
        self._add_action(media_menu, "Open File...", "Ctrl+O", self.action_open_file)
        self._add_action(media_menu, "Open Multiple Files...", "Ctrl+Shift+F", self.action_open_file)
        self._add_action(media_menu, "Open Folder...", "Ctrl+Shift+O", self.action_open_folder)
        self._add_action(media_menu, "Open Disc...", None, self._stub_not_supported)
        self._add_action(media_menu, "Open Network Stream...", "Ctrl+N", self.action_open_url)
        self._add_action(media_menu, "Open Capture Device...", None, self._stub_not_supported)
        self.recent_menu = media_menu.addMenu("Open Recent Media")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        media_menu.addSeparator()
        self._add_action(media_menu, "Save Playlist to File...", "Ctrl+Y", self._export_playlist)
        media_menu.addSeparator()
        self._add_action(media_menu, "Quit", "Ctrl+Q", self.close)

        playback_menu = menu_bar.addMenu("&Playback")
        self._add_action(playback_menu, "Play / Pause", "Space", self.engine.toggle_play_pause)
        self._add_action(playback_menu, "Stop", None, self.engine.stop)
        self._add_action(playback_menu, "Previous", None, self.action_previous)
        self._add_action(playback_menu, "Next", None, self.action_next)
        playback_menu.addSeparator()
        self._add_action(playback_menu, "Jump Forward 10s", "Right", lambda: self.engine.seek_relative(10_000))
        self._add_action(playback_menu, "Jump Backward 10s", "Left", lambda: self.engine.seek_relative(-10_000))
        playback_menu.addSeparator()
        speed_menu = playback_menu.addMenu("Speed")
        for speed in (0.25, 0.5, 1.0, 1.25, 1.5, 2.0, 3.0):
            self._add_action(speed_menu, f"{speed}x", None, lambda _c=False, s=speed: self.engine.set_rate(s))
        self._add_action(playback_menu, "Frame by Frame", "E", self.engine.next_frame)
        playback_menu.addSeparator()
        self.record_action = self._add_action(
            playback_menu, "Record", "Ctrl+R", self.action_toggle_record, checkable=True
        )
        playback_menu.addSeparator()
        repeat_group = QActionGroup(self)
        repeat_group.setExclusive(True)
        self.repeat_off_action = self._add_action(
            playback_menu,
            "No Repeat",
            None,
            lambda: self._set_repeat_mode(REPEAT_OFF),
            checkable=True,
            group=repeat_group,
        )
        self.repeat_one_action = self._add_action(
            playback_menu,
            "Repeat One",
            None,
            lambda: self._set_repeat_mode(REPEAT_ONE),
            checkable=True,
            group=repeat_group,
        )
        self.repeat_all_action = self._add_action(
            playback_menu,
            "Repeat All",
            None,
            lambda: self._set_repeat_mode(REPEAT_ALL),
            checkable=True,
            group=repeat_group,
        )
        self.shuffle_action = self._add_action(playback_menu, "Random", None, self._on_shuffle_action, checkable=True)
        playback_menu.addSeparator()
        self._add_action(playback_menu, "Add Bookmark", None, self.action_add_bookmark)

        audio_menu = menu_bar.addMenu("&Audio")
        self.audio_track_menu = audio_menu.addMenu("Audio Track")
        self.audio_track_menu.aboutToShow.connect(self._populate_audio_track_menu)
        audio_menu.addSeparator()
        self._add_action(audio_menu, "Increase Volume", "Up", lambda: self._bump_volume(5))
        self._add_action(audio_menu, "Decrease Volume", "Down", lambda: self._bump_volume(-5))
        self._add_action(audio_menu, "Mute", "M", self._on_mute_toggled)
        audio_menu.addSeparator()
        self._add_action(audio_menu, "Audio Delay +50ms", None, lambda: self._adjust_audio_delay(50))
        self._add_action(audio_menu, "Audio Delay -50ms", None, lambda: self._adjust_audio_delay(-50))

        video_menu = menu_bar.addMenu("&Video")
        self._add_action(video_menu, "Fullscreen", "F", self.toggle_fullscreen)
        self.always_on_top_action = self._add_action(
            video_menu, "Always on Top", None, self.toggle_always_on_top, checkable=True
        )
        self._add_action(video_menu, "Picture in Picture", None, self.toggle_pip)
        self._add_action(video_menu, "Minimal View", "Ctrl+H", self.toggle_mini_player)
        video_menu.addSeparator()
        zoom_menu = video_menu.addMenu("Zoom")
        for label, scale in (("50%", 0.5), ("100%", 1.0), ("200%", 2.0), ("Fit Window", 0.0)):
            self._add_action(zoom_menu, label, None, lambda _c=False, s=scale: self.engine.set_zoom(s))
        aspect_menu = video_menu.addMenu("Aspect Ratio")
        for ratio in ("Auto", "16:9", "4:3", "1:1", "21:9"):
            self._add_action(
                aspect_menu,
                ratio,
                None,
                lambda _c=False, r=ratio: self.engine.set_aspect_ratio(None if r == "Auto" else r),
            )
        crop_menu = video_menu.addMenu("Crop")
        for ratio in ("None", "16:9", "4:3", "1.85:1", "2.35:1"):
            self._add_action(
                crop_menu, ratio, None, lambda _c=False, r=ratio: self.engine.set_crop(None if r == "None" else r)
            )
        rotate_menu = video_menu.addMenu("Rotate")
        for degrees in (0, 90, 180, 270):
            self._add_action(rotate_menu, f"{degrees}°", None, lambda _c=False, d=degrees: self.engine.set_rotation(d))
        self._add_action(video_menu, "Mirror", None, self.engine.set_mirror, checkable=True)
        video_menu.addSeparator()
        adjust_menu = video_menu.addMenu("Color Adjustments")
        for name in ("brightness", "contrast", "gamma", "hue", "saturation"):
            self._add_action(
                adjust_menu, name.title() + "...", None, lambda _c=False, n=name: self._prompt_adjustment(n)
            )
        video_menu.addSeparator()
        self._add_action(video_menu, "Take Snapshot", "Shift+S", self.action_take_screenshot)

        subtitle_menu = menu_bar.addMenu("Su&btitle")
        self._add_action(subtitle_menu, "Add Subtitle File...", None, self.action_load_subtitle)
        self.subtitle_track_menu = subtitle_menu.addMenu("Sub Track")
        self.subtitle_track_menu.aboutToShow.connect(self._populate_subtitle_track_menu)
        subtitle_menu.addSeparator()
        self._add_action(subtitle_menu, "Sub Delay +100ms", None, lambda: self._adjust_subtitle_delay(100))
        self._add_action(subtitle_menu, "Sub Delay -100ms", None, lambda: self._adjust_subtitle_delay(-100))

        tools_menu = menu_bar.addMenu("&Tools")
        self._add_action(tools_menu, "Effects and Filters...", "Ctrl+E", self.action_open_equalizer)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "Media Information...", "Ctrl+I", self.action_show_media_info)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "Preferences...", "Ctrl+P", self.action_open_settings)

        view_menu = menu_bar.addMenu("&View")
        self.playlist_action = self._add_action(
            view_menu, "Playlist", "Ctrl+L", self._toggle_playlist_panel, checkable=True
        )
        self._add_action(view_menu, "Add to Favorites", None, self.action_add_favorite)
        view_menu.addSeparator()
        self._add_action(view_menu, "Sleep Timer...", None, self.action_set_sleep_timer)

        help_menu = menu_bar.addMenu("&Help")
        self._add_action(help_menu, "About...", None, lambda: AboutDialog(self).exec())

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        shortcut: str | None,
        handler,
        checkable: bool = False,
        group: QActionGroup | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if group:
            group.addAction(action)
        action.triggered.connect(handler)
        menu.addAction(action)
        return action

    def _stub_not_supported(self) -> None:
        QMessageBox.information(self, "Not Available", "This feature isn't implemented in this build.")

    # ---- Signal wiring -----------------------------------------------------------------------
    def _wire_signals(self) -> None:
        c = self.controls_bar
        c.play_pause_clicked.connect(self.engine.toggle_play_pause)
        c.stop_clicked.connect(self.engine.stop)
        c.previous_clicked.connect(self.action_previous)
        c.next_clicked.connect(self.action_next)
        c.seek_requested.connect(self.engine.seek_ms)
        c.volume_changed.connect(self._on_volume_changed)
        c.mute_toggled.connect(self._on_mute_toggled)
        c.fullscreen_toggled.connect(self.toggle_fullscreen)
        c.playlist_toggled.connect(self._toggle_playlist_panel)
        c.loop_toggled.connect(self._on_loop_toggled)
        c.shuffle_toggled.connect(self._on_shuffle_toggled)

        self.engine.position_changed.connect(self._on_position_changed)
        self.engine.state_changed.connect(self._on_state_changed)
        self.engine.media_changed.connect(self._on_media_changed)
        self.engine.error_occurred.connect(self._on_error)

        self.playlist.items_changed.connect(self._refresh_playlist_panel)
        self.playlist.current_index_changed.connect(self._on_playlist_index_changed)

        self.playlist_panel.item_activated.connect(self._on_playlist_item_activated)
        self.playlist_panel.item_removed.connect(self.playlist.remove_at)
        self.playlist_panel.items_reordered.connect(self.playlist.move)
        self.playlist_panel.save_requested.connect(self.playlist.save_playlist)
        self.playlist_panel.load_requested.connect(self._on_load_playlist)
        self.playlist_panel.import_requested.connect(self.playlist.import_from_m3u)
        self.playlist_panel.export_requested.connect(self.playlist.export_to_m3u)

        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        shortcuts = self.settings.get("shortcuts")
        bindings = {
            "exit_fullscreen": self._exit_fullscreen_only,
            "history": lambda: self._show_side_tab(self.history_page),
        }
        self._shortcuts = []
        for action_name, handler in bindings.items():
            key_sequence = shortcuts.get(action_name)
            if key_sequence:
                shortcut = QShortcut(QKeySequence(key_sequence), self)
                shortcut.activated.connect(handler)
                self._shortcuts.append(shortcut)

    # ---- Browse pages / library scan -----------------------------------------------------------
    def _refresh_browse_pages(self) -> None:
        recent = self.history.get_recent(30)
        self.history_page.populate([(f"{r['title']}", r["path"]) for r in recent])

        favorites = self.history.get_favorites()
        self.favorites_page.populate([(f["title"], f["path"]) for f in favorites])

        library_folders = self.settings.get("library_folders") or []
        videos, music = [], []
        for folder in library_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                continue
            for file_path in folder_path.rglob("*"):
                if not file_path.is_file() or not is_media_file(file_path):
                    continue
                entry = (file_path.name, str(file_path))
                if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                    videos.append(entry)
                else:
                    music.append(entry)
        self.library_videos_page.populate(videos)
        self.library_music_page.populate(music)

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        for row in self.history.get_recent(10):
            action = QAction(row["title"], self)
            action.triggered.connect(lambda _c=False, p=row["path"]: self._play_path(p))
            self.recent_menu.addAction(action)

    def _populate_audio_track_menu(self) -> None:
        self.audio_track_menu.clear()
        for track_id, label in self.engine.get_audio_tracks():
            action = QAction(label, self)
            action.triggered.connect(lambda _c=False, t=track_id: self.engine.set_audio_track(t))
            self.audio_track_menu.addAction(action)

    def _populate_subtitle_track_menu(self) -> None:
        self.subtitle_track_menu.clear()
        for track_id, label in self.subtitles.get_tracks():
            action = QAction(label, self)
            action.triggered.connect(lambda _c=False, t=track_id: self.subtitles.set_track(t))
            self.subtitle_track_menu.addAction(action)

    # ---- File/folder/url opening ----------------------------------------------------------
    def action_open_file(self) -> None:
        filters = (
            "Media Files (*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm *.mpeg *.mpg *.3gp *.ts "
            "*.mp3 *.aac *.wav *.flac *.ogg *.m4a);;All Files (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Media", "", filters)
        if paths:
            self.playlist.add_many(paths)
            self._play_path(paths[0])

    def action_open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if not folder:
            return
        folder_path = Path(folder)
        media_files = sorted(str(p) for p in folder_path.rglob("*") if p.is_file() and is_media_file(p))
        if not media_files:
            QMessageBox.information(self, "Open Folder", "No supported media files found in this folder.")
            return
        library_folders = self.settings.get("library_folders") or []
        if folder not in library_folders:
            library_folders.append(folder)
            self.settings.set("library_folders", library_folders)
        self.playlist.add_many(media_files)
        self._play_path(media_files[0])
        self._refresh_browse_pages()

    def action_open_url(self) -> None:
        dialog = OpenUrlDialog(self)
        if dialog.exec() and dialog.url():
            url = dialog.url()
            self.playlist.add(url)
            self._play_path(url)

    def action_load_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Subtitle", "", "Subtitles (*.srt *.ass *.ssa *.vtt)")
        if path:
            self.subtitles.load_external(path)

    def _export_playlist(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "playlist.m3u", "Playlists (*.m3u)")
        if path:
            self.playlist.export_to_m3u(path)

    # ---- Playback orchestration -----------------------------------------------------------
    def _play_path(self, path: str) -> None:
        if not path:
            return
        if path not in self.playlist.items:
            self.playlist.add(path)
        self.playlist.set_current(self.playlist.items.index(path))
        self.now_playing_label.setText(Path(path).name if "://" not in path else path)

        resume_ms = self.history.get_resume_position(path) if self.settings.get("resume_playback") else 0
        self.engine.load(path, start_ms=resume_ms)

        if self.settings.get("remember_subtitle"):
            self.subtitles.auto_load_for(path)
        self._refresh_playlist_panel()
        QTimer.singleShot(0, self._embed_video)

    def _embed_video(self) -> None:
        win_id = int(self.video_canvas.winId())
        platform = "win32" if sys.platform.startswith("win") else ("darwin" if sys.platform == "darwin" else "linux")
        self.engine.attach_to_widget(win_id, platform)

    def action_previous(self) -> None:
        path = self.playlist.previous()
        if path:
            self._play_path(path)

    def action_next(self) -> None:
        path = self.playlist.next()
        if path:
            self._play_path(path)

    def _on_playlist_item_activated(self, index: int) -> None:
        items = self.playlist.items
        if 0 <= index < len(items):
            self._play_path(items[index])

    def _on_load_playlist(self, name: str) -> None:
        if self.playlist.load_playlist(name):
            path = self.playlist.current_path()
            if path:
                self._play_path(path)

    # ---- Engine event handlers --------------------------------------------------------------
    def _on_position_changed(self, current_ms: int, duration_ms: int) -> None:
        self.controls_bar.set_position(current_ms)
        self.controls_bar.set_duration(duration_ms)
        path = self.engine.current_path()
        if path:
            self.history.update_position(path, current_ms)

    def _on_state_changed(self, state: str) -> None:
        self.controls_bar.set_playing(state == "playing")
        if state == "ended":
            self.action_next()

    def _on_media_changed(self, path: str) -> None:
        title = Path(path).name if "://" not in path else path
        self.history.record_play(path, title)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "Playback Error", message)

    def _on_volume_changed(self, value: int) -> None:
        self.engine.set_volume(value)
        self.controls_bar.set_volume_display(value, self.engine.is_muted())
        self.settings.set("volume", value)

    def _bump_volume(self, delta: int) -> None:
        new_value = max(0, min(150, self.controls_bar.volume_slider.value() + delta))
        self.controls_bar.volume_slider.setValue(new_value)

    def _on_mute_toggled(self) -> None:
        self.engine.set_muted(not self.engine.is_muted())
        self.settings.set("muted", self.engine.is_muted())
        self.controls_bar.set_volume_display(self.engine.get_volume(), self.engine.is_muted())

    def _set_repeat_mode(self, mode: str) -> None:
        self.playlist.set_repeat(mode)
        self.settings.set("loop_mode", mode)
        self.controls_bar.set_loop_icon(mode)

    def _on_loop_toggled(self) -> None:
        order = [REPEAT_OFF, REPEAT_ALL, REPEAT_ONE]
        next_mode = order[(order.index(self.playlist.repeat_mode) + 1) % len(order)]
        self._set_repeat_mode(next_mode)
        {REPEAT_OFF: self.repeat_off_action, REPEAT_ONE: self.repeat_one_action, REPEAT_ALL: self.repeat_all_action}[
            next_mode
        ].setChecked(True)

    def _on_shuffle_toggled(self) -> None:
        enabled = self.controls_bar.shuffle_btn.isChecked()
        self.playlist.set_shuffle(enabled)
        self.settings.set("shuffle", enabled)
        self.shuffle_action.setChecked(enabled)

    def _on_shuffle_action(self) -> None:
        enabled = self.shuffle_action.isChecked()
        self.controls_bar.shuffle_btn.setChecked(enabled)
        self.playlist.set_shuffle(enabled)
        self.settings.set("shuffle", enabled)

    def _on_playlist_index_changed(self, _index: int) -> None:
        self._refresh_playlist_panel()

    def _refresh_playlist_panel(self) -> None:
        self.playlist_panel.set_items(self.playlist.items, self.playlist.current_index())

    def _toggle_playlist_panel(self) -> None:
        visible = not self.side_tabs.isVisible()
        self.side_tabs.setVisible(visible)
        self.playlist_action.setChecked(visible)
        if visible:
            self.side_tabs.setCurrentWidget(self.playlist_panel)

    def _show_side_tab(self, widget: QWidget) -> None:
        self.side_tabs.show()
        self.playlist_action.setChecked(True)
        self.side_tabs.setCurrentWidget(widget)

    # ---- Subtitle / audio / video adjustment helpers ----------------------------------------
    def _adjust_subtitle_delay(self, delta_ms: int) -> None:
        self.subtitles.set_delay_ms(self.subtitles.delay_ms + delta_ms)

    def _adjust_audio_delay(self, delta_ms: int) -> None:
        current = self.settings.get("audio_delay_ms") + delta_ms
        self.settings.set("audio_delay_ms", current)
        self.engine.set_audio_delay(current)

    def _prompt_adjustment(self, name: str) -> None:
        value, ok = QInputDialog.getDouble(self, name.title(), f"{name.title()} (-100 to 100):", 0, -100, 100, 1)
        if ok:
            self.engine.set_adjustment(name, value)

    def action_open_equalizer(self) -> None:
        def on_change(enabled: bool, gains: list[float], preamp: float) -> None:
            if enabled:
                self.engine.enable_equalizer(gains, preamp)
            else:
                self.engine.disable_equalizer()

        EqualizerDialog(on_change, self).exec()

    def action_show_media_info(self) -> None:
        path = self.engine.current_path() or "No media loaded"
        info = (
            f"Path: {path}\n"
            f"Duration: {self.engine.get_duration_ms() / 1000:.1f}s\n"
            f"Audio tracks: {self.engine.get_audio_tracks()}\n"
            f"Subtitle tracks: {self.engine.get_subtitle_tracks()}\n"
            f"Playback rate: {self.engine.get_rate()}x\n"
        )
        MediaInfoDialog(info, self).exec()

    def action_add_bookmark(self) -> None:
        path = self.engine.current_path()
        if not path:
            return
        label, ok = QInputDialog.getText(self, "Add Bookmark", "Label:")
        if ok:
            self.history.add_bookmark(path, label or "Bookmark", self.engine.get_time_ms())

    def action_add_favorite(self) -> None:
        path = self.engine.current_path()
        if path:
            self.history.add_favorite(path, Path(path).name)
            self._refresh_browse_pages()

    def action_take_screenshot(self) -> None:
        screenshots_dir = Path.home() / "Pictures" / "AuroraPlayer Screenshots"
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        ok = self.engine.take_snapshot(str(screenshots_dir / filename))
        if ok:
            QMessageBox.information(self, "Screenshot", f"Saved to {screenshots_dir / filename}")

    def action_toggle_record(self) -> None:
        if not self._is_recording:
            self._is_recording = True
            self._record_start_ms = self.engine.get_time_ms()
        else:
            self._is_recording = False
            end_ms = self.engine.get_time_ms()
            path = self.engine.current_path()
            if path and "://" not in path:
                clips_dir = Path.home() / "Videos" / "AuroraPlayer Clips"
                out_path = clips_dir / f"clip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                self.engine.record_clip(path, str(out_path), self._record_start_ms, end_ms)
            else:
                QMessageBox.information(self, "Record Clip", "Clip recording requires a local file.")

    def action_set_sleep_timer(self) -> None:
        minutes, ok = QInputDialog.getInt(self, "Sleep Timer", "Stop playback after (minutes):", 30, 0, 600)
        if ok and minutes > 0:
            self._sleep_timer.start(minutes * 60 * 1000)

    def _on_sleep_timer(self) -> None:
        self.engine.pause()

    # ---- Window chrome: fullscreen / always-on-top / mini player / pip -----------
    def toggle_always_on_top(self) -> None:
        is_on_top = self.always_on_top_action.isChecked()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, is_on_top)
        self.show()

    def toggle_fullscreen(self) -> None:
        if self._is_fullscreen:
            self._exit_fullscreen_only()
        else:
            self._is_fullscreen = True
            self.menuBar().hide()
            self.statusBar().hide()
            self.side_tabs.hide()
            self.showFullScreen()
            self._hide_controls_timer.start()

    def _exit_fullscreen_only(self) -> None:
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False
        self.menuBar().show()
        self.statusBar().show()
        self.showNormal()
        self._hide_controls_timer.stop()
        self.controls_bar.fade_in()

    def _auto_hide_controls(self) -> None:
        if self._is_fullscreen:
            self.controls_bar.fade_out()

    def mouseMoveEvent(self, event):
        if self._is_fullscreen:
            self.controls_bar.fade_in()
            self._hide_controls_timer.start()
        super().mouseMoveEvent(event)

    def toggle_mini_player(self) -> None:
        if self.menuBar().isVisible():
            self.menuBar().hide()
            self.statusBar().hide()
            self.side_tabs.hide()
            self.resize(420, 280)
        else:
            self.menuBar().show()
            self.statusBar().show()
            self.resize(self.settings.get("window_width"), self.settings.get("window_height"))

    def toggle_pip(self) -> None:
        if self._pip_window is None:
            self._pip_window = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self._pip_window.setAttribute(Qt.WA_NativeWindow, True)
            self._pip_window.setFixedSize(360, 203)
            self._pip_window.setStyleSheet("background-color: black;")
            self._pip_window.show()
            win_id = int(self._pip_window.winId())
            platform = (
                "win32" if sys.platform.startswith("win") else ("darwin" if sys.platform == "darwin" else "linux")
            )
            self.engine.attach_to_widget(win_id, platform)
        else:
            self._pip_window.close()
            self._pip_window = None
            QTimer.singleShot(0, self._embed_video)

    # ---- Drag and drop ---------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
        media_paths = [p for p in paths if is_media_file(Path(p))]
        if media_paths:
            self.playlist.add_many(media_paths)
            self._play_path(media_paths[0])
        event.acceptProposedAction()

    # ---- Settings dialog / window state persistence -----------------------------------------
    def action_open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.engine.set_subtitle_delay(self.settings.get("subtitle_delay_ms"))
            self.engine.set_audio_delay(self.settings.get("audio_delay_ms"))

    def _restore_window_state(self) -> None:
        width = self.settings.get("window_width")
        height = self.settings.get("window_height")
        self.resize(width, height)
        self.controls_bar.set_volume_display(self.settings.get("volume"), self.settings.get("muted"))
        self.engine.set_volume(self.settings.get("volume"))
        self.controls_bar.set_loop_icon(self.playlist.repeat_mode)
        self.controls_bar.shuffle_btn.setChecked(self.playlist.shuffle)
        if self.settings.get("window_maximized"):
            self.showMaximized()

    def closeEvent(self, event):
        self.settings.set("window_width", self.width())
        self.settings.set("window_height", self.height())
        self.settings.set("window_maximized", self.isMaximized())
        path = self.engine.current_path()
        if path:
            self.history.update_position(path, self.engine.get_time_ms())
        self.session.shutdown()
        super().closeEvent(event)
