"""Local product artwork, indexed by packaging level and normalized product name."""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImageReader, QPixmap

IMAGE_ROOT = Path(__file__).resolve().parent / "images"
LEVELS = ("carton", "inner", "display", "unit")


def normalize_product_name(name):
    return re.sub(r"[\s_]+", " ", unicodedata.normalize("NFKC", str(name))).strip().casefold()


class AvatarCatalog:
    def __init__(self, root=IMAGE_ROOT):
        self.root = Path(root).resolve()
        self.index = {level: {} for level in LEVELS}
        # Existing images directly in images/ are unit avatars. Other levels
        # have their own folders so a unit bottle never becomes a carton image.
        for level in LEVELS:
            folders = [self.root / level]
            if level == "unit":
                folders.insert(0, self.root)
            for folder in folders:
                for path in sorted(folder.glob("*")):
                    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                        self.index[level][normalize_product_name(path.stem)] = path
        manifest = self.root / "avatars.json"
        if manifest.exists():
            try:
                mappings = json.loads(manifest.read_text(encoding="utf-8"))
                for level in LEVELS:
                    for product, relative in mappings.get(level, {}).items():
                        path = (self.root / relative).resolve()
                        if path.is_relative_to(self.root) and path.is_file():
                            self.index[level][normalize_product_name(product)] = path
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                print(f"Could not load avatar mappings: {exc}")

    def resolve(self, level, products):
        products = {normalize_product_name(name) for name in products if name}
        # Mixed-product boxes must not suggest they contain just one product.
        if len(products) != 1:
            return None
        return self.index.get(level, {}).get(next(iter(products)))


@lru_cache(maxsize=128)
def avatar_pixmap(path, size=44):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        reader.setScaledSize(original.scaled(QSize(size * 2, size * 2), Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return QPixmap()
    pixmap = QPixmap.fromImage(image).scaled(size * 2, size * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(2)
    return pixmap
