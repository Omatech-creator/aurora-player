"""Playlist side panel: drag-and-drop reordering, repeat/shuffle toggles, save/load."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PlaylistPanel(QWidget):
    """A thin view over PlaylistManager; the manager remains the source of truth."""

    item_activated = Signal(int)  # double-clicked row index -> play
    item_removed = Signal(int)
    items_reordered = Signal(int, int)  # from_index, to_index
    save_requested = Signal(str)
    load_requested = Signal(str)
    import_requested = Signal(str)
    export_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaylistPanel")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Playlist")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_clicked)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._on_load_clicked)
        header.addWidget(save_btn)
        header.addWidget(load_btn)
        layout.addLayout(header)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.itemDoubleClicked.connect(self._on_double_clicked)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget, 1)

        footer = QHBoxLayout()
        import_btn = QPushButton("Import M3U")
        import_btn.clicked.connect(self._on_import_clicked)
        export_btn = QPushButton("Export M3U")
        export_btn.clicked.connect(self._on_export_clicked)
        footer.addWidget(import_btn)
        footer.addWidget(export_btn)
        layout.addLayout(footer)

    # ---- Population --------------------------------------------------------------------------
    def set_items(self, paths: list[str], current_index: int = -1) -> None:
        self.list_widget.clear()
        for index, path in enumerate(paths):
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            if index == current_index:
                item.setText("▶  " + item.text())
            self.list_widget.addItem(item)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        self.item_activated.emit(self.list_widget.row(item))

    def _on_rows_moved(self, _parent, start, _end, _dest_parent, dest_row) -> None:
        self.items_reordered.emit(start, dest_row if dest_row < start else dest_row - 1)

    def _show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from playlist")
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        if action == remove_action:
            self.item_removed.emit(self.list_widget.row(item))

    def _on_save_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Playlist", "Playlist name:")
        if ok and name.strip():
            self.save_requested.emit(name.strip())

    def _on_load_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "Load Playlist", "Playlist name:")
        if ok and name.strip():
            self.load_requested.emit(name.strip())

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Playlist", "", "Playlists (*.m3u *.m3u8)")
        if path:
            self.import_requested.emit(path)

    def _on_export_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Playlist", "playlist.m3u", "Playlists (*.m3u)")
        if path:
            self.export_requested.emit(path)
