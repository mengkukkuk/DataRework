import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtGui import QFont, QFontDatabase, QRawFont
from PySide6.QtWidgets import QApplication

from i18n import CATALOGS, language
from login_window import LoginWindow
from main_window import MainWindow
from theme import _render_stylesheet
from typography import ui_font_family


class TypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # Windows offscreen Qt does not enumerate system fonts. Register existing
        # OS fonts in this test process only; never install or download fonts.
        cls.font_ids = []
        for name in ("LeelawUI.ttf", "LeelaUIb.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.exists():
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id >= 0:
                    cls.font_ids.append(font_id)
        ui_font_family.cache_clear()

    @classmethod
    def tearDownClass(cls):
        for font_id in cls.font_ids:
            QFontDatabase.removeApplicationFont(font_id)
        ui_font_family.cache_clear()

    def setUp(self):
        saved = language.code
        settings = patch("i18n.QSettings")
        settings.start()
        self.addCleanup(settings.stop)
        self.addCleanup(language.set, saved)
        language.set("en")
        if not QFontDatabase.families(QFontDatabase.Thai):
            self.skipTest("No Thai font installed for visual metric checks")

    def keep(self, window):
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_selected_family_covers_english_and_thai_catalog_characters(self):
        font = QRawFont.fromFont(QFont(ui_font_family()))
        chars = set("DataRework 0123456789" + "".join(CATALOGS["th"].values()))
        required = {char for char in chars if 0x0E01 <= ord(char) <= 0x0E5B or char.isascii() and char.isalnum()}
        self.assertTrue(font.isValid())
        self.assertTrue(all(font.supportsCharacter(ord(char)) for char in required))

    @patch("db.get_columns", return_value=[])
    @patch("db.fetch_distinct_values", return_value=[])
    def test_language_switch_keeps_action_widths_and_pending_data(self, *mocks):
        window = self.keep(MainWindow("tester", "admin", "TEST"))
        window._populate_table(["id", "unit_serial_no"], [(1, "UNIT-001")], ["id"])
        window.table.item(0, 2).setText("UNIT-แก้ไข")
        window.show()
        self.app.processEvents()
        buttons = [window.save_btn, window.cancel_btn, window.rename_btn, window.search_btn]
        sizes = [(button.sizeHint().width(), button.height()) for button in buttons]
        pending = window._collect_changes()
        family = window.save_btn.font().family()

        language.set("th")
        self.app.processEvents()

        self.assertEqual(sizes, [(button.sizeHint().width(), button.height()) for button in buttons])
        self.assertEqual(window.save_btn.font().family(), family)
        self.assertEqual(window._collect_changes(), pending)
        self.assertGreaterEqual(window.table.rowHeight(0), window.table.fontMetrics().height() + 10)

    def test_login_fields_and_button_fit_thai_text_in_both_themes(self):
        window = self.keep(LoginWindow())
        language.set("th")
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                window.setStyleSheet(_render_stylesheet(theme, "login.css"))
                window.show()
                self.app.processEvents()
                for widget in (window.username_input, window.password_input, window.login_button):
                    self.assertEqual(widget.font().family(), ui_font_family())
                    self.assertGreaterEqual(widget.height(), widget.fontMetrics().height() + 12)
                self.assertGreaterEqual(window.login_button.height(), 46)


if __name__ == "__main__":
    unittest.main()
