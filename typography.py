"""Shared English/Thai typography using fonts already installed on the device."""
from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase, QRawFont


# Prefer a family that draws both scripts itself, avoiding mixed-font baselines.
FONT_CANDIDATES = ("Leelawadee UI", "Noto Sans Thai", "Tahoma", "Thonburi", "Leelawadee")
GLYPH_SAMPLE = "DataRework 0123456789 ภาษาไทย กิ กี กึ กื กุ กู ก่ ก้ ก๊ ก๋ ญ ฐ ำ"
TYPE_SIZES = {"body": 14, "small": 13, "caption": 12, "title": 24, "dialog": 20}


@lru_cache(maxsize=1)
def ui_font_family():
    """Resolve after QApplication exists; keep the same family on EN/TH switches."""
    available = set(QFontDatabase.families())
    candidates = list(FONT_CANDIDATES) + QFontDatabase.families(QFontDatabase.Thai)
    for family in dict.fromkeys(candidates):
        if family not in available:
            continue
        raw = QRawFont.fromFont(QFont(family))
        if raw.isValid() and all(raw.supportsCharacter(ord(char)) for char in GLYPH_SAMPLE):
            return family
    # Qt keeps its normal script fallback if no single installed family qualifies.
    return QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()


def ui_font():
    font = QFont()
    font.setFamilies([ui_font_family(), "Segoe UI Symbol", "DejaVu Sans"])
    font.setPixelSize(TYPE_SIZES["body"])
    font.setStyleHint(QFont.SansSerif)
    return font
