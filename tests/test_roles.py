import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import db
from main_window import MainWindow


class AdminRoleTests(unittest.TestCase):
    def test_admin_and_super_admin_are_admin_roles(self):
        for role in ("admin", "ADMIN", "super admin", "Super Admin", "super_admin", "super-admin", " super  admin "):
            self.assertTrue(db.is_admin_role(role), role)

    def test_other_roles_are_not_admin_roles(self):
        for role in ("user", "operator", "", None, "superadmin2", "administrator"):
            self.assertFalse(db.is_admin_role(role), role)

    @patch("db.get_columns", return_value=[])
    @patch("db.fetch_distinct_values", return_value=[])
    def test_main_window_grants_admin_rights_to_super_admin(self, *mocks):
        QApplication.instance() or QApplication([])
        for role, expected in (("admin", True), ("super admin", True), ("user", False)):
            win = MainWindow("tester", role, "TEST-OPERATOR")
            self.assertEqual(win.is_admin, expected, role)
            win.deleteLater()


if __name__ == "__main__":
    unittest.main()
