import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from main_window import MainWindow


COLUMNS = ["id", "created_at", "assignment_no", "product_name",
           "unit_serial_no", "unit_source_id", "carton_serial_no"]


class IdentifierValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.columns = patch("db.get_columns", return_value=COLUMNS).start()
        self.values = patch("db.fetch_distinct_values", return_value=[]).start()
        self.win = MainWindow("tester", "admin", "TEST-OPERATOR")

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        patch.stopall()

    def test_category_immediately_offers_all_serials_and_allows_typing(self):
        self.values.return_value = [f"SERIAL-{n:04}" for n in range(350)] + [None, ""]
        self.win.category_combo.setCurrentIndex(self.win.category_combo.findData("unit"))
        self.assertEqual(self.win.tag_combo.currentData(), "serial_no")
        self.assertEqual(self.win.tag_value_combo.count(), 350)
        self.assertEqual(self.win.tag_value_edit.text(), "")
        self.assertIsNone(self.values.call_args.kwargs["limit"])
        self.assertEqual(self.values.call_args.args[1], "unit_serial_no")
        self.win.tag_value_combo.setCurrentIndex(349)
        self.assertEqual(self.win.tag_value_edit.text(), "SERIAL-0349")
        condition = self.win._category_tag_condition(COLUMNS)
        self.assertEqual(condition[0][1], ["SERIAL-0349"])
        self.win.tag_value_edit.setText("custom-value")
        self.assertEqual(self.win._category_tag_condition(COLUMNS)[0][1], ["custom-value"])

    def test_tag_and_upstream_filters_refresh_choices(self):
        self.win.category_combo.setCurrentIndex(self.win.category_combo.findData("unit"))
        self.win.tag_value_edit.setText("old-serial")
        self.values.return_value = [0, 12]
        self.win.tag_combo.setCurrentIndex(self.win.tag_combo.findData("source_id"))
        self.assertEqual(self.win.tag_value_combo.itemText(0), "0")
        self.assertEqual(self.win.tag_value_edit.text(), "")
        self.assertEqual(self.values.call_args.args[1], "unit_source_id")
        self.win.job_combo.setCurrentText("JOB-1")
        self.win.product_name_combo.setCurrentText("Product A")
        self.win.tag_value_edit.setText("12")
        self.win.product_name_combo.lineEdit().editingFinished.emit()
        params = [p for _, values in self.values.call_args.kwargs["conditions"] for p in values]
        self.assertIn("JOB-1", params)
        self.assertIn("Product A", params)
        self.assertIn(self.win.month_combo.currentData(), params)
        self.assertEqual(self.win.tag_value_edit.text(), "12")
        self.win._on_clear()
        self.assertEqual(self.win.tag_value_combo.count(), 0)
        self.assertFalse(self.win.tag_value_combo.isEnabled())

    def test_failed_lookup_keeps_manual_input_available(self):
        self.values.side_effect = RuntimeError("offline")
        self.win.category_combo.setCurrentIndex(self.win.category_combo.findData("unit"))
        self.assertTrue(self.win.tag_value_combo.isEnabled())
        self.assertEqual(self.win.tag_value_combo.count(), 0)
        self.assertEqual(self.win.status_label.property("state"), "error")
        self.win.tag_value_edit.setText("manual")
        self.assertEqual(self.win._category_tag_condition(COLUMNS)[0][1], ["manual"])


if __name__ == "__main__":
    unittest.main()
