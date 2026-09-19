import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from psycopg2 import sql
import db
from container_panel import ContainerPanel, build_hierarchy
from i18n_widgets import QPushButton
from main_window import MainWindow


GROUPS = [("C1", "I1", "D1", "U1", 2), ("C1", "I1", "D1", "U2", 1),
          ("C2", "I1", "D1", "U1", 1), (None, None, "D3", "U3", 1)]
COLUMNS = ["id", "carton_serial_no", "inner_serial_no", "display_serial_no", "unit_serial_no"]


class ContainerPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_paths_do_not_merge_shared_serials_or_lose_missing_parents(self):
        root = build_hierarchy(GROUPS)
        self.assertEqual(root.rows, 5)
        self.assertEqual(root.children["C1"].rows, 3)
        self.assertEqual(root.children["C2"].rows, 1)
        self.assertIn("D3", root.children[None].children[None].children)
        unit = root.children["C1"].children["I1"].children["D1"].children["U1"]
        self.assertEqual(unit.rows, 2)

    def test_rename_is_available_on_every_named_level(self):
        panel = ContainerPanel(True)
        panel.set_groups(GROUPS)
        requested = []
        panel.rename_requested.connect(lambda *args: requested.append(args))
        for path, level, serial in [((), "carton", "C1"), (("C1",), "inner", "I1"),
                                    (("C1", "I1"), "display", "D1"),
                                    (("C1", "I1", "D1"), "unit", "U1")]:
            panel.navigate(path)
            button = panel.cards[0].findChild(QPushButton, "linkBtn")
            self.assertTrue(button.isEnabled())
            button.click()
            self.assertEqual(requested[-1], (level, serial))
        panel.navigate(())
        self.assertFalse(panel.cards[-1].findChild(QPushButton, "linkBtn").isEnabled())
        panel.deleteLater()

    def test_unit_rename_updates_serial_state_in_same_transaction(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        with patch("db.connection.get_connection", return_value=conn), patch(
            "db.containers._serial_in_use", return_value=False
        ), patch("db.containers._container_edge_counts", return_value=(1, 0)), patch(
            "db.containers._apply_serial_rename", return_value=1
        ) as rename, patch("db.containers._set_serial_active") as active:
            result = db.rename_container("unit", "U1", "U-new")
        rename.assert_called_once_with(cur, "unit", "U1", "U-new", "public", "filling_product_logs")
        self.assertEqual([call.args[2:] for call in active.call_args_list], [("U1", False), ("U-new", True)])
        conn.commit.assert_called_once()
        self.assertEqual(result, {"rows": 1, "edges": 1})

    def test_unit_dialog_keeps_clicked_serial_outside_picker_limit(self):
        from rename_dialog import RenameContainerDialog
        with patch("db.container_serials", return_value=["OTHER"]), patch(
            "db.container_rename_preview", return_value={"rows": 1, "edges": 1}
        ):
            dialog = RenameContainerDialog(level="unit", serial="U-clicked")
            self.assertEqual(dialog.level, "unit")
            self.assertEqual(dialog.values(), ("U-clicked", "U-clicked"))
            dialog.new_edit.setText("U-new")
            self.assertTrue(dialog.confirm_btn.isEnabled())
            dialog.deleteLater()

    def test_navigation_search_pagination_and_permissions(self):
        panel = ContainerPanel(False)
        panel.set_groups(GROUPS)
        panel.navigate(("C1", "I1", "D1"))
        self.assertEqual(len(panel.cards), 2)
        result = []
        panel.records_requested.connect(result.append)
        panel.cards[0].findChildren(QPushButton)[0].click()
        self.assertEqual(result, [("C1", "I1", "D1", "U1")])
        panel.navigate(())
        rename = panel.cards[0].findChild(QPushButton, "linkBtn")
        self.assertFalse(rename.isEnabled())
        panel.set_groups([(f"C{i:03}", "I", "D", "U", 1) for i in range(30)])
        self.assertEqual(len(panel.cards), 20)
        panel.next.click()
        self.assertEqual(len(panel.cards), 10)
        panel.search.setText("C029")
        self.assertEqual(len(panel.cards), 1)
        panel.set_groups([])
        self.assertEqual(panel.path, ())
        panel.deleteLater()

    @patch("db.get_columns", return_value=COLUMNS)
    @patch("db.fetch_distinct_values", return_value=[])
    @patch("db.container_groups", return_value=GROUPS)
    def test_main_window_preserves_pending_edits_and_routes_full_path(self, *mocks):
        win = MainWindow("tester", "admin")
        win._populate_table(["id", "unit_serial_no"], [(1, "U1")], ["id"])
        win.table.item(0, 2).setText("EDITED")
        before = win._collect_changes()
        win.views.setCurrentIndex(1)
        self.assertEqual(win._collect_changes(), before)
        with patch.object(win, "_on_search") as search:
            win._open_container_records(("C1", "I1"))
            search.assert_not_called()
        win.table.item(0, 2).setText("U1")
        with patch("db.get_primary_key_columns", return_value=["id"]), patch(
            "db.query_rows", return_value=(COLUMNS, [])
        ) as rows:
            win._open_container_records(("C1", "I1"))
            conditions = rows.call_args.args[2]
            self.assertEqual([values for _, values in conditions][-2:], [["C1"], ["I1"]])
            self.assertEqual(win.views.currentIndex(), 0)
        win.deleteLater()

    def test_page_buttons_and_resize_keep_all_cards_reachable_without_scrolling(self):
        panel = ContainerPanel(True)
        panel.inner.resize(1800, 480)
        panel._fit_page()
        panel.set_groups([(f"C{i:03}", "I", "D", "U", 1) for i in range(24)])
        self.assertEqual(panel.page_size, 20)
        self.assertEqual(len(panel.cards), 20)
        self.assertFalse(panel.previous.isEnabled())
        self.assertTrue(panel.next.isEnabled())
        panel.next.click()
        self.assertEqual(len(panel.cards), 4)
        self.assertTrue(panel.previous.isEnabled())
        self.assertFalse(panel.next.isEnabled())
        panel.inner.resize(1050, 240)
        panel._fit_page()
        self.assertEqual(panel.page_size, 8)
        self.assertEqual(panel.page, 2)
        self.assertEqual(len(panel.cards), 8)
        panel.previous.click()
        self.assertEqual(panel.page, 1)
        panel.previous.click()
        self.assertEqual(panel.page, 0)
        self.assertFalse(panel.previous.isEnabled())
        panel.deleteLater()

    def test_database_aggregation_is_parameterized_and_has_no_record_limit(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = GROUPS
        with patch("db.connection.get_connection", return_value=conn):
            result = db.container_groups("logs", COLUMNS, [(sql.SQL("product_name = %s"), ["A'B"])])
        self.assertEqual(result, GROUPS)
        query, params = cursor.execute.call_args.args
        self.assertEqual(params, ["A'B"])
        self.assertNotIn("LIMIT", repr(query))
        self.assertIn("GROUP BY", repr(query))
        conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
