"""Undo/redo of unsaved grid edits, and the grid going back to the saved values
when a save is refused (main_window.MainWindow)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

import psycopg2
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import db
from debug_log import LOG
from i18n import tr
from main_window import MainWindow

COLUMNS = ["id", "unit_serial_no"]
ROWS = [(1, "U1"), (2, "U2"), (3, "U3")]


@patch("db.get_columns", return_value=COLUMNS)
@patch("db.fetch_distinct_values", return_value=[])
class EditHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        win = MainWindow("tester", "admin", "TEST-OPERATOR")
        win._populate_table(COLUMNS, list(ROWS), ["id"])
        return win

    @staticmethod
    def _cell(win, row):
        return win.table.item(row, 2).text()  # col 0 is Del, col 1 is id

    # -- undo / redo -----------------------------------------------------------

    def test_buttons_start_disabled_and_follow_the_history(self, *mocks):
        win = self._window()
        self.assertFalse(win.undo_btn.isEnabled())
        self.assertFalse(win.redo_btn.isEnabled())
        win.table.item(0, 2).setText("X")
        self.assertTrue(win.undo_btn.isEnabled())
        self.assertFalse(win.redo_btn.isEnabled())
        win.undo_btn.click()
        self.assertEqual(self._cell(win, 0), "U1")
        self.assertFalse(win.undo_btn.isEnabled())
        self.assertTrue(win.redo_btn.isEnabled())
        win.redo_btn.click()
        self.assertEqual(self._cell(win, 0), "X")
        win.deleteLater()

    def test_undo_walks_back_one_edit_at_a_time(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("A")
        win.table.item(0, 2).setText("B")
        win.table.item(1, 2).setText("C")
        win._undo()
        self.assertEqual((self._cell(win, 0), self._cell(win, 1)), ("B", "U2"))
        win._undo()
        self.assertEqual(self._cell(win, 0), "A")
        win._undo()
        self.assertEqual(self._cell(win, 0), "U1")
        self.assertEqual(win._collect_changes(), ([], []))  # nothing pending any more
        win.deleteLater()

    def test_a_new_edit_after_undo_drops_the_redo_history(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("A")
        win._undo()
        win.table.item(0, 2).setText("B")
        self.assertFalse(win.redo_btn.isEnabled())
        win.deleteLater()

    def test_undo_restores_the_edited_highlight_state(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("A")
        self.assertNotEqual(win.table.item(0, 2).background().style(), Qt.NoBrush)
        win._undo()
        self.assertEqual(win.table.item(0, 2).background().style(), Qt.NoBrush)
        win.deleteLater()

    def test_marking_rows_for_deletion_undoes_as_one_step(self, *mocks):
        win = self._window()
        selection = win.table.selectionModel()
        for row in (0, 1):
            selection.select(win.table.model().index(row, 0),
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)
        win._delete_selected_rows()
        self.assertEqual(len(win._collect_changes()[1]), 2)
        self.assertEqual(len(win._history_undo), 1)
        win._undo()
        self.assertEqual(win._collect_changes(), ([], []))
        win._redo()
        self.assertEqual(len(win._collect_changes()[1]), 2)
        win.deleteLater()

    def test_ticking_del_by_hand_is_undoable(self, *mocks):
        win = self._window()
        win.table.item(2, 0).setCheckState(Qt.Checked)
        self.assertEqual(win._collect_changes()[1], [(3,)])
        win._undo()
        self.assertEqual(win._collect_changes(), ([], []))
        win.deleteLater()

    def test_sorting_is_not_an_edit_and_undo_still_finds_the_row(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("Z9")          # U1 -> Z9, on row 0
        win._on_header_clicked(2)                    # sort ascending by unit_serial_no
        win._on_header_clicked(2)                    # ...descending: Z9 comes first
        win.table.item(2, 2).setText("A0")           # a different row, after the sorts
        self.assertEqual(len(win._history_undo), 2)  # the two sorts added nothing
        win._undo()
        win._undo()
        self.assertEqual(win._collect_changes(), ([], []))
        self.assertEqual(sorted(self._cell(win, r) for r in range(3)), ["U1", "U2", "U3"])
        win.deleteLater()

    def test_loading_rows_clears_the_history(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("A")
        win._populate_table(COLUMNS, list(ROWS), ["id"])
        self.assertFalse(win.undo_btn.isEnabled())
        win._undo()  # nothing to do, and nothing breaks
        self.assertEqual(self._cell(win, 0), "U1")
        win.deleteLater()

    def test_buttons_are_only_offered_on_the_records_tab(self, *mocks):
        win = self._window()
        win.show()
        self.assertTrue(win.undo_btn.isVisible())
        win.views.setCurrentIndex(1)
        self.assertFalse(win.undo_btn.isVisible())
        self.assertFalse(win.redo_btn.isVisible())
        win.views.setCurrentIndex(0)
        self.assertTrue(win.undo_btn.isVisible())
        win.close()
        win.deleteLater()

    # -- a refused save puts the old values back --------------------------------

    def _save(self, win, error):
        with patch("main_window.QMessageBox.question", return_value=QMessageBox.Yes), \
                patch("db.save_grid_changes", side_effect=error):
            win._on_save()

    def test_a_refused_save_shows_the_old_values_again_and_says_why(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("U-DMG")
        win.table.item(1, 0).setCheckState(Qt.Checked)
        error = db.SerialUnavailableError('Serial "U-DMG" is damaged and cannot be used.')
        before = len(LOG.entries)
        self._save(win, error)
        self.assertEqual([self._cell(win, r) for r in range(3)], ["U1", "U2", "U3"])
        self.assertEqual(win._collect_changes(), ([], []))
        self.assertIn('"U-DMG" is damaged', win.status_label.text())
        self.assertIn(str(tr("Reverted to the saved values. Undo brings your edits back.")),
                      win.status_label.text())
        self.assertEqual(win.status_label.property("state"), "error")
        self.assertEqual(len(LOG.entries), before + 1)
        win.deleteLater()

    def test_every_blocked_kind_reverts(self, *mocks):
        for error in (db.SharedEdgeError("shared"), db.SerialConflictError("dup"),
                      db.SerialInventoryError("missing")):
            win = self._window()
            win.table.item(0, 2).setText("EDIT")
            self._save(win, error)
            self.assertEqual(self._cell(win, 0), "U1", type(error).__name__)
            win.deleteLater()

    def test_undo_after_a_refused_save_brings_the_edits_back(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("EDIT")
        win.table.item(2, 0).setCheckState(Qt.Checked)
        self._save(win, db.SerialInventoryError("refused"))
        self.assertEqual(win._collect_changes(), ([], []))
        win._undo()
        updates, deletes = win._collect_changes()
        self.assertEqual(updates, [((1,), {"unit_serial_no": "EDIT"})])
        self.assertEqual(deletes, [(3,)])
        win.deleteLater()

    def test_an_unreachable_database_keeps_the_edits_for_a_retry(self, *mocks):
        win = self._window()
        win.table.item(0, 2).setText("EDIT")
        self._save(win, psycopg2.OperationalError("down"))
        self.assertEqual(self._cell(win, 0), "EDIT")
        win.deleteLater()


if __name__ == "__main__":
    unittest.main()
