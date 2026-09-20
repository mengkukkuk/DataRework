import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from login_window import LoginWindow
from main_window import MainWindow, STAGING_TABLE
from i18n_widgets import QMessageBox


class UserTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, window):
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    @patch("db.authenticate", return_value=None)
    def test_rejected_login_does_not_unpack_result_or_emit_success(self, authenticate):
        window = self.window(LoginWindow())
        window.username_input.setText("missing-user")
        window.password_input.setText("invalid")
        successes = []
        window.login_succeeded.connect(lambda *args: successes.append(args))

        window._attempt_login()

        authenticate.assert_called_once_with("missing-user", "invalid")
        self.assertEqual(successes, [])
        self.assertEqual(window.password_input.text(), "")
        self.assertFalse(window.error_label.isHidden())

    @patch("db.authenticate", return_value=("admin", "TEST-OPERATOR"))
    def test_login_passes_permission_and_tag_to_controller(self, authenticate):
        window = self.window(LoginWindow())
        window.username_input.setText("tester")
        window.password_input.setText("password")
        successes = []
        window.login_succeeded.connect(lambda *args: successes.append(args))

        window._attempt_login()

        self.assertEqual(successes, [("tester", "admin", "TEST-OPERATOR")])

    @patch("db.get_columns", return_value=[])
    @patch("db.fetch_distinct_values", return_value=[])
    def test_save_passes_operator_tag_without_replacing_schema(self, *mocks):
        window = self.window(MainWindow("tester", "admin", "TEST-OPERATOR"))
        window._populate_table(["id", "unit_serial_no"], [(1, "OLD")], ["id"])
        window.table.item(0, 2).setText("NEW")

        with patch("main_window.QMessageBox.question", return_value=QMessageBox.Yes), \
                patch("db.save_grid_changes") as save, \
                patch.object(window, "_on_search") as refresh:
            window._on_save()

        save.assert_called_once_with(
            STAGING_TABLE, ["id"], [((1,), {"unit_serial_no": "NEW"})], [],
            tag_name="TEST-OPERATOR",
        )
        refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
