"""Shared palette and QSS rendering for the main and login windows."""
import os
import re
import tempfile

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF

def _generate_dropdown_arrow_icon(color, theme_name):
    """A small solid down-triangle PNG for QComboBox's drop-down arrow, one
    per theme since the color has to invert for a light background. Qt's QSS
    doesn't render the usual CSS border-triangle trick as a triangle (it just
    paints a filled block), so this draws one directly instead."""
    path = os.path.join(tempfile.gettempdir(), f"datarework_combo_arrow_{theme_name}.png")
    image = QImage(20, 20, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(QPolygonF([QPointF(4, 7), QPointF(16, 7), QPointF(10, 14)]))
    painter.end()
    image.save(path)
    return path.replace("\\", "/")


# THEMES (the two color palettes) and the QSS template both live in
# style.css, next to this file — see that file's header comment for why
# they're written as :root[data-theme="..."] custom-property blocks even
# though Qt's QSS engine can't use CSS variables natively: this module
# parses them itself and does the __token__ substitution below, so Qt only
# ever sees a flat stylesheet with literal values, exactly as before.
_THEME_BLOCK_RE = re.compile(r':root\[data-theme=["\'](\w+)["\']\]\s*\{([^}]*)\}', re.DOTALL)
_CSS_VAR_RE = re.compile(r'--([\w-]+)\s*:\s*([^;]+);')

def _load_style_source():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    themes = {}
    for match in _THEME_BLOCK_RE.finditer(content):
        theme_name, body = match.group(1), match.group(2)
        themes[theme_name] = {
            key.replace("-", "_"): value.strip()
            for key, value in _CSS_VAR_RE.findall(body)
        }

    template = _THEME_BLOCK_RE.sub("", content).strip()
    return themes, template


THEMES, STYLE_TEMPLATE = _load_style_source()


def _render_stylesheet(theme_name, extra_stylesheet=None):
    theme = THEMES[theme_name]
    arrow_icon_path = _generate_dropdown_arrow_icon(theme["arrow_color"], theme_name)
    css = STYLE_TEMPLATE
    if extra_stylesheet:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), extra_stylesheet)
        with open(path, encoding="utf-8") as source:
            css += "\n" + source.read()
    for token, value in theme.items():
        css = css.replace(f"__{token}__", value)
    return css.replace("__arrow_icon_path__", arrow_icon_path)


