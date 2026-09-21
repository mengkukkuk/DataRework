"""One drawn mark per packaging level, so a card says what it is before it is read.

The four levels are the only thing on a container card that never appears in the
text the same way twice -- "Carton"/"ลัง" is a word, and a serial is just digits --
so each level gets a silhouette and a colour of its own: a sealed crate, a box
inside a box, an open tray of standing units, and a single bottle. Nesting is
legible in the shapes themselves, biggest to smallest.

The marks are painted here rather than shipped as files for the same reason the
dropdown arrow in theme.py is: one small vector per level, wanted at a handful of
sizes, on two backgrounds. The colours are fixed brand accents, not theme tokens --
like the Search/Save chips in style.css, they are chosen to read on both the dark
(#101722) and the light (#ffffff) panel.
"""
from functools import lru_cache

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

LEVELS = ("carton", "inner", "display", "unit")

LEVEL_COLORS = {
    "carton": "#d1873c",   # amber: the outermost crate
    "inner": "#8d74d8",    # violet
    "display": "#4f9bd9",  # the house blue, for the level users open most
    "unit": "#34a06c",     # the save green: a single physical item
}

# Everything below is drawn in this box and scaled to the size asked for, so the
# strokes keep their proportions at 14px in a breadcrumb and 22px on a card.
_CANVAS = 24.0


def level_color(level):
    return LEVEL_COLORS.get(level, "#5b9bd5")


def _carton(path):
    """A sealed crate: body, lid seam, and the flap join above it."""
    path.addRect(QRectF(3.4, 5.6, 17.2, 14.0))
    path.moveTo(3.4, 10.2)
    path.lineTo(20.6, 10.2)
    path.moveTo(12.0, 5.6)
    path.lineTo(12.0, 10.2)


def _inner(path):
    """A box inside a box."""
    path.addRect(QRectF(3.4, 4.8, 17.2, 14.8))
    path.addRect(QRectF(8.2, 9.4, 7.6, 6.0))


def _display(path):
    """An open tray with three units standing in it."""
    path.addRect(QRectF(3.4, 12.6, 17.2, 7.0))
    for x in (8.0, 12.0, 16.0):
        path.moveTo(x, 12.6)
        path.lineTo(x, 6.2)


def _unit(path):
    """One bottle: neck, shoulders, body, label band."""
    path.moveTo(10.2, 4.4)
    path.lineTo(13.8, 4.4)
    path.lineTo(13.8, 7.4)
    path.lineTo(16.0, 10.2)
    path.lineTo(16.0, 19.6)
    path.lineTo(8.0, 19.6)
    path.lineTo(8.0, 10.2)
    path.lineTo(10.2, 7.4)
    path.closeSubpath()
    path.moveTo(8.0, 13.4)
    path.lineTo(16.0, 13.4)


_SHAPES = {"carton": _carton, "inner": _inner, "display": _display, "unit": _unit}


@lru_cache(maxsize=64)
def level_mark(level, size=20, color=None):
    """The mark for `level` as a QPixmap `size` logical pixels square.

    Painted at twice the size and handed back with a device pixel ratio of 2, so
    the strokes stay clean on a HiDPI screen and downscale smoothly elsewhere.
    """
    draw = _SHAPES.get(level)
    tint = QColor(color or level_color(level))
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.transparent)
    if draw is None:
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    path = QPainterPath()
    draw(path)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size * ratio / _CANVAS, size * ratio / _CANVAS)
    # A wash of the same colour behind the strokes, so the mark reads as a chip
    # rather than as wireframe, on a white panel as well as a near-black one.
    fill = QColor(tint)
    fill.setAlpha(46)
    painter.fillPath(path, fill)
    pen = QPen(tint, 1.7)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawPath(path)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


@lru_cache(maxsize=64)
def level_icon(level, size=16):
    return QIcon(level_mark(level, size))
