"""Generate the Inkstone icon set.

Draws the logo — an ink drop on a paper page with a folded corner — with
QPainter (no extra deps; PySide6 is already a runtime dependency) and writes:

  packaging/icon.png        256px PNG (AppImage / window icon)
  packaging/icon.ico        multi-size ICO (16/32/48/64/128/256, PNG-compressed)
  packaging/icon-preview.png  row of rendered sizes for a quick visual check
  images/logo.png           256px PNG used by the README

Run from the repo root (headless-safe):
  QT_QPA_PLATFORM=offscreen python packaging/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QImageWriter, QPainter, QPainterPath

PAPER = QColor("#f6f1e7")
PAPER_EDGE = QColor("#d8d0bf")
FOLD = QColor("#e3dccb")
INK = QColor("#241f4e")
INK_HIGHLIGHT = QColor("#4c46a0")

SIZES = (16, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = float(size)
    # Page geometry (normalized to the 256 design grid).
    left, top = 0.16 * s, 0.08 * s
    right, bottom = 0.84 * s, 0.92 * s
    r = 0.055 * s          # corner radius
    fold = 0.20 * s        # folded-corner size

    # Page outline with three rounded corners and a cut top-right corner.
    page = QPainterPath()
    page.moveTo(left + r, top)
    page.lineTo(right - fold, top)
    page.lineTo(right, top + fold)
    page.lineTo(right, bottom - r)
    page.arcTo(QRectF(right - 2 * r, bottom - 2 * r, 2 * r, 2 * r), 0, -90)
    page.lineTo(left + r, bottom)
    page.arcTo(QRectF(left, bottom - 2 * r, 2 * r, 2 * r), 270, -90)
    page.lineTo(left, top + r)
    page.arcTo(QRectF(left, top, 2 * r, 2 * r), 180, -90)
    page.closeSubpath()

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(PAPER)
    p.drawPath(page)

    # Edge stroke (skip at 16px where it just muddies).
    if size >= 32:
        p.setPen(PAPER_EDGE)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(page)
        p.setPen(Qt.PenStyle.NoPen)

    # Fold flap.
    flap = QPainterPath()
    flap.moveTo(right - fold, top)
    flap.lineTo(right, top + fold)
    flap.lineTo(right - fold, top + fold)
    flap.closeSubpath()
    p.setBrush(FOLD)
    p.drawPath(flap)

    # Ink drop: teardrop with a pointed top flowing into a round body.
    cx, cy = 0.5 * s, 0.60 * s
    dr = 0.165 * s        # body radius
    tip_y = 0.30 * s
    drop = QPainterPath()
    drop.moveTo(cx, tip_y)
    drop.cubicTo(cx + 0.30 * dr, cy - 1.55 * dr, cx + dr, cy - 0.95 * dr, cx + dr, cy)
    drop.arcTo(QRectF(cx - dr, cy - dr, 2 * dr, 2 * dr), 0, -180)
    drop.cubicTo(cx - dr, cy - 0.95 * dr, cx - 0.30 * dr, cy - 1.55 * dr, cx, tip_y)
    drop.closeSubpath()
    p.setBrush(INK)
    p.drawPath(drop)

    # Specular highlight on the drop (visible 32px and up).
    if size >= 32:
        p.setBrush(INK_HIGHLIGHT)
        hr = 0.045 * s
        p.drawEllipse(QPointF(cx - 0.45 * dr, cy - 0.25 * dr), hr, hr * 1.5)

    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    QImageWriter(buf, b"png").write(img)
    data = buf.data().data()
    return data if isinstance(data, bytes) else bytes(data)


def write_ico(path: Path, images: dict[int, bytes]) -> None:
    """Pack PNG blobs into a .ico container (PNG entries; Vista+)."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    offset = 6 + 16 * count
    blobs = b""
    for size in sorted(images):
        data = images[size]
        b = size if size < 256 else 0
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    QGuiApplication(sys.argv)
    root = Path(__file__).resolve().parent.parent

    rendered = {size: draw(size) for size in SIZES}

    draw(256).save(str(root / "packaging" / "icon.png"))
    (root / "images").mkdir(exist_ok=True)
    draw(256).save(str(root / "images" / "logo.png"))
    write_ico(root / "packaging" / "icon.ico",
              {size: png_bytes(img) for size, img in rendered.items()})

    # Preview strip: each size on a neutral background.
    pad = 12
    width = sum(SIZES) + pad * (len(SIZES) + 1)
    height = max(SIZES) + 2 * pad
    strip = QImage(width, height, QImage.Format.Format_ARGB32)
    strip.fill(QColor("#3a3f44"))
    p = QPainter(strip)
    x = pad
    for size in SIZES:
        p.drawImage(x, (height - size) // 2, rendered[size])
        x += size + pad
    p.end()
    strip.save(str(root / "packaging" / "icon-preview.png"))

    print("Wrote icon.png, icon.ico, images/logo.png, icon-preview.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
