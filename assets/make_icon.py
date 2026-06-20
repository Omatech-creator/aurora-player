"""Generates the Aurora Player application icon (app_icon.ico + app_icon.png).

Design: a rounded-square tile with a blue→indigo "aurora" gradient, a soft glow,
and a white play triangle. Rendered at multiple sizes and packed into a .ico so
Windows picks the crispest size for the taskbar, title bar and Explorer.

Run once:  python assets/make_icon.py
"""

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient

ICON_DIR = Path(__file__).resolve().parent / "icons"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    margin = size * 0.06
    radius = size * 0.24
    tile = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

    # Background gradient (aurora blue -> indigo).
    grad = QLinearGradient(tile.topLeft(), tile.bottomRight())
    grad.setColorAt(0.0, QColor("#3D8BFD"))
    grad.setColorAt(0.55, QColor("#4361EE"))
    grad.setColorAt(1.0, QColor("#7048E8"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(tile, radius, radius)

    # Soft inner glow near the top-left for depth.
    glow = QRadialGradient(QPointF(size * 0.36, size * 0.32), size * 0.55)
    glow.setColorAt(0.0, QColor(255, 255, 255, 70))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(tile, radius, radius)

    # White play triangle, centered and optically balanced.
    cx, cy = size / 2, size / 2
    r = size * 0.20
    triangle = QPolygonF(
        [
            QPointF(cx - r * 0.75, cy - r),
            QPointF(cx - r * 0.75, cy + r),
            QPointF(cx + r, cy),
        ]
    )
    p.setBrush(QColor("#FFFFFF"))
    p.setPen(QPen(QColor(0, 0, 0, 30), max(1.0, size * 0.01)))
    p.drawPolygon(triangle)

    p.end()
    return img


def write_ico(images: list[QImage], path: Path) -> None:
    """Pack multiple PNG-encoded images into a single .ico container."""
    import struct

    png_blobs = []
    for img in images:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        png_blobs.append((img.width(), bytes(ba)))

    count = len(png_blobs)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=1 (icon), count
    entries = b""
    offset = 6 + count * 16
    for width, blob in png_blobs:
        w = 0 if width >= 256 else width
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with path.open("wb") as f:
        f.write(header)
        f.write(entries)
        for _, blob in png_blobs:
            f.write(blob)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    images = [render(s) for s in SIZES]
    write_ico(images, ICON_DIR / "app_icon.ico")
    render(256).save(str(ICON_DIR / "app_icon.png"), "PNG")
    print(f"Wrote {ICON_DIR / 'app_icon.ico'} and app_icon.png")


if __name__ == "__main__":
    main()
