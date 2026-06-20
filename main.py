"""Application entry point: bootstraps Qt, applies the theme, and shows the main window."""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

BASE_DIR = Path(__file__).resolve().parent
STYLE_PATH = BASE_DIR / "styles" / "dark_theme.qss"
ICON_PATH = BASE_DIR / "assets" / "icons" / "app_icon.ico"


def load_stylesheet(accent_color: str) -> str:
    try:
        raw = STYLE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    return raw.replace("@ACCENT@", accent_color)


def _set_windows_app_id() -> None:
    """Tell Windows this is its own app so the taskbar shows our icon, not python's."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AuroraPlayer.Media.1")
        except Exception:
            pass


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Aurora Player")

    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = MainWindow()
    app.setStyleSheet(load_stylesheet(window.settings.get("accent_color")))
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
