import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import string
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from i18n import CATALOGS, language, tr
from login_window import LoginWindow
from main_window import MainWindow
from rename_dialog import RenameContainerDialog, ChildRelabelDialog


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.saved_language = language.code
        self.settings = patch("i18n.QSettings").start()
        language.set("en")
        self.windows = []

    def tearDown(self):
        language.set(self.saved_language)
        for window in self.windows:
            window.close()
            window.deleteLater()
        patch.stopall()

    def test_catalog_parity_and_parameters(self):
        self.assertEqual(CATALOGS["en"].keys(), CATALOGS["th"].keys())
        formatter = string.Formatter()
        for key, english in CATALOGS["en"].items():
            fields = lambda text: {f for _, f, _, _ in formatter.parse(text) if f is not None}
            self.assertEqual(fields(english), fields(CATALOGS["th"][key]), key)
        language.set("th")
        self.assertEqual(tr("unknown_custom_column"), "unknown_custom_column")

    @patch("db.get_columns", return_value=["id", "unit_serial_no", "product_name"])
    @patch("db.fetch_distinct_values", return_value=[])
    def test_switch_preserves_edits_filters_and_identifiers(self, *mocks):
        win = MainWindow("tester", "admin")
        self.windows.append(win)
        win._populate_table(["id", "unit_serial_no", "product_name"],
                            [(1, "SERIAL", "Search"), (2, "OTHER", "Save")], ["id"])
        win.table.item(0, 2).setText("EDITED")
        win.table.item(1, 0).setCheckState(Qt.Checked)
        win.product_name_combo.setCurrentText("Search")
        win.category_combo.setCurrentIndex(win.category_combo.findData("unit"))
        win.tag_combo.setCurrentIndex(win.tag_combo.findData("serial_no"))
        win.tag_value_edit.setText("RAW")
        win._column_checks["product_name"].setChecked(False)
        before = win._collect_changes()
        month = win.month_combo.currentData()
        win._show_status(tr("{p0} row(s) loaded.", p0=2))
        language.set("th")
        self.assertEqual(win.search_btn.text(), "ค้นหา")
        self.assertEqual(win.table.horizontalHeaderItem(2).text(), "รหัสซีเรียล (หน่วยสินค้า)")
        self.assertEqual(win.product_name_combo.lineEdit().placeholderText(), "ชื่อผลิตภัณฑ์")
        self.assertEqual(win.status_label.text(), "โหลดแล้ว 2 แถว")
        self.assertEqual(win.product_name_combo.currentText(), "Search")
        self.assertEqual(win.category_combo.currentData(), "unit")
        self.assertEqual(win.tag_combo.currentData(), "serial_no")
        self.assertEqual(win.tag_value_edit.text(), "RAW")
        self.assertEqual(win.month_combo.currentData(), month)
        self.assertEqual(win._collect_changes(), before)
        self.assertTrue(win.table.isColumnHidden(3))
        self.assertEqual(win.table.item(0, 3).text(), "Search")
        language.set("en")
        self.assertEqual(win.search_btn.text(), "Search")
        self.assertEqual(win.table.horizontalHeaderItem(2).text(), "unit_serial_no")
        self.assertEqual(win._collect_changes(), before)
        self.settings.return_value.setValue.assert_called_with("language", "en")

    @patch("db.container_serials", return_value=["OLD"])
    @patch("db.container_rename_preview", return_value={"rows": 2, "edges": 1})
    def test_login_and_rename_dialogs(self, *mocks):
        login = LoginWindow()
        rename = RenameContainerDialog()
        child = ChildRelabelDialog(None, "carton", "OLD", "NEW",
                                  [{"level": "inner", "serial_no": "OLD-1", "children": 2}])
        self.windows.extend([login, rename, child])
        login.username_input.setText("Username")
        login._show_error(tr("Invalid username or password"))
        rename.new_edit.setText("NEW")
        language.set("th")
        self.assertEqual(login.login_button.text(), "เข้าสู่ระบบ")
        self.assertEqual(login.username_input.text(), "Username")
        self.assertEqual(rename.confirm_btn.text(), "เปลี่ยนรหัส")
        self.assertEqual(rename._level_buttons["carton"].text(), "ลัง")
        self.assertEqual(rename.values(), ("OLD", "NEW"))
        self.assertEqual(child.apply_btn.text(), "ใช้การเปลี่ยนแปลง 1 รายการ")
        self.assertEqual(child.renames(), [("inner", "OLD-1", "NEW-1")])
        language.set("en")
        self.assertEqual(child.apply_btn.text(), "Apply 1 change(s)")


if __name__ == "__main__":
    unittest.main()
