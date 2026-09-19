import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from container_panel import ContainerPanel, build_hierarchy
from i18n_widgets import QLabel
from product_avatars import AvatarCatalog, avatar_pixmap

PRODUCT = "Matte Poreless รองพื้น _01 Silky Ivory"


class ProductAvatarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_image_matches_normalized_product_only_at_unit_level(self):
        catalog = AvatarCatalog()
        path = catalog.resolve("unit", ["  matte poreless รองพื้น 01 Silky Ivory "])
        self.assertIsNotNone(path)
        self.assertFalse(avatar_pixmap(path).isNull())
        self.assertIsNone(catalog.resolve("carton", [PRODUCT]))
        self.assertIsNone(catalog.resolve("unit", ["Matte Poreless"]))
        self.assertIsNone(catalog.resolve("unit", [PRODUCT, "Other product"]))

    def test_metadata_follows_full_path_without_changing_counts(self):
        groups = [("C", "I", "D", "U1", 2, [PRODUCT]),
                  ("C", "I", "D", "U2", 3, ["Other"])]
        root = build_hierarchy(groups)
        self.assertEqual(root.rows, 5)
        self.assertEqual(root.children["C"].products, {PRODUCT, "Other"})
        panel = ContainerPanel(True)
        panel.set_groups(groups)
        panel.navigate(("C", "I", "D"))
        self.assertIsNotNone(panel.cards[0].findChild(QLabel, "productAvatar"))
        self.assertIsNone(panel.cards[1].findChild(QLabel, "productAvatar"))
        panel.deleteLater()

    def test_level_specific_manifest_alias(self):
        root = Path(__file__).resolve().parent.parent / "images"
        filename = PRODUCT + ".png"
        with patch.object(Path, "read_text", return_value=json.dumps({"carton": {"Alias": filename}})):
            catalog = AvatarCatalog(root)
            self.assertEqual(catalog.resolve("carton", ["Alias"]), root / filename)
            self.assertIsNone(catalog.resolve("unit", ["Alias"]))


if __name__ == "__main__":
    unittest.main()
