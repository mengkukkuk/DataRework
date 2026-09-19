import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange

from main_window import MainWindow, DELETED_ROW_BG


class BulkDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patch("db.get_columns", return_value=[]).start()
        patch("db.fetch_distinct_values", return_value=[]).start()
        self.save = patch("db.save_grid_changes").start()
        self.win = MainWindow("tester", "admin")
        self.win._populate_table(["id", "unit_serial_no"],
                                 [(1, "C"), (2, "A"), (3, "B")], ["id"])

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        patch.stopall()

    def test_range_delete_marks_rows_without_writing_and_can_be_undone(self):
        self.assertFalse(self.win.delete_btn.isEnabled())
        self.win.table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 2), True)
        self.assertTrue(self.win.delete_btn.isEnabled())
        self.win.delete_btn.click()
        self.assertEqual(self.win._collect_changes(), ([], [(1,), (2,)]))
        self.assertEqual(self.win.table.item(0, 2).background().color(), DELETED_ROW_BG)
        self.assertEqual(self.win.table.rowCount(), 3)
        self.save.assert_not_called()
        self.assertFalse(self.win.delete_btn.isEnabled())
        self.win.table.item(0, 0).setCheckState(Qt.Unchecked)
        self.assertEqual(self.win._collect_changes(), ([], [(2,)]))

    def test_disjoint_selection_after_sort_targets_correct_primary_keys(self):
        self.win._on_header_clicked(2)
        selection = self.win.table.selectionModel()
        for row in (0, 2):
            selection.select(self.win.table.model().index(row, 1),
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.win.delete_btn.click()
        self.assertEqual(set(self.win._collect_changes()[1]), {(2,), (1,)})

    def test_permission_and_primary_key_guards(self):
        self.win.table.selectAll()
        self.win.is_admin = False
        self.win._update_delete_button()
        self.assertFalse(self.win.delete_btn.isEnabled())
        self.win._delete_selected_rows()
        self.assertEqual(self.win._collect_changes(), ([], []))
        self.win.is_admin = True
        self.win._populate_table(["unit_serial_no"], [("A",)], [])
        self.win.table.selectAll()
        self.assertFalse(self.win.delete_btn.isEnabled())
        self.win._delete_selected_rows()
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
