"""'Delete container…': the pick-and-review dialog, the main-window flow, the card link.

The dialog is exercised for real (offscreen); db calls are patched because they need
a database. The db behaviour itself is covered by test_container_delete.py.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch

import psycopg2
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QMessageBox

import db
from container_panel import ContainerPanel
from debug_log import LOG
from delete_dialog import DeleteContainerDialog
from i18n_widgets import QLabel, QPushButton
from main_window import MainWindow

PREVIEW = {
    "level": "display", "serial_no": "D1",
    "children": [
        {"serial_no": "U1", "level": "unit", "depth": 1, "children": 0},
        {"serial_no": "U2", "level": "unit", "depth": 1, "children": 0},
    ],
    "rows": 2, "edges": 3, "units": 2,
    "emptied": [{"level": "inner", "serial_no": "I1"}],
}
NESTED = dict(PREVIEW, level="inner", serial_no="I1", emptied=[], children=[
    {"serial_no": "D1", "level": "display", "depth": 1, "children": 1},
    {"serial_no": "U1", "level": "unit", "depth": 2, "children": 0},
])
DELETED = {"rows": 2, "edges": 3, "units": 2, "emptied": []}


def listed(dialog):
    """[(serial, left indent)] of the items the dialog lists as being inside."""
    return [(row.findChild(QLabel, "insideSerial").text(), row.layout().contentsMargins().left())
            for row in dialog.findChildren(QFrame, "childRow")]


class DeleteDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.serials = patch("db.container_serials", return_value=["D1", "D2"]).start()
        self.preview = patch("db.container_delete_preview", return_value=PREVIEW).start()

    def tearDown(self):
        patch.stopall()

    def make(self, **kwargs):
        options = dict(table="fpl_test", level="display", serial="D1")
        options.update(kwargs)
        dialog = DeleteContainerDialog(None, **options)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_lists_what_is_inside_the_chosen_container_indented_by_depth(self):
        self.preview.return_value = NESTED
        dialog = self.make(level="inner", serial="I1")
        shown = listed(dialog)
        self.assertEqual([serial for serial, _ in shown], ["D1", "U1"])
        self.assertLess(shown[0][1], shown[1][1])

    def test_shows_the_totals_and_the_parents_that_would_be_removed_too(self):
        dialog = self.make()
        totals = dialog.summary.text()
        for number in ("2", "3"):
            self.assertRegex(totals, rf"\b{number}\b")
        self.assertIn("I1", dialog.emptied_label.text())
        self.assertTrue(dialog.delete_btn.isEnabled())

    def test_previews_against_the_configured_table(self):
        self.make()
        self.preview.assert_called_with("display", "D1", table="fpl_test")

    def test_delete_stays_disabled_when_the_container_cannot_be_resolved(self):
        self.preview.side_effect = db.ContainerDeleteError("linked under more than one parent")
        dialog = self.make()
        self.assertFalse(dialog.delete_btn.isEnabled())
        self.assertEqual(listed(dialog), [])
        self.assertIn("more than one parent", dialog.summary.text())

    def test_delete_stays_disabled_until_a_serial_is_chosen(self):
        self.serials.return_value = []
        dialog = self.make(serial="")
        self.assertFalse(dialog.delete_btn.isEnabled())

    def test_enter_never_confirms_the_delete(self):
        # Barcode scanners end a scan with Enter; that must not delete anything.
        dialog = self.make()
        for key in (Qt.Key_Return, Qt.Key_Enter):
            QTest.keyClick(dialog.serial_combo.lineEdit(), key)
        self.assertNotEqual(dialog.result(), QDialog.Accepted)
        self.assertFalse(dialog.delete_btn.isDefault())

    def test_only_carton_inner_and_display_are_offered_in_that_order(self):
        dialog = self.make()
        buttons = dialog.findChild(QFrame, "levelSeg").findChildren(QPushButton)
        self.assertEqual(len(buttons), 3)
        picked = []
        for button in buttons:
            button.click()
            picked.append(dialog.level)
        self.assertEqual(picked, ["carton", "inner", "display"])

    def test_switching_level_reloads_the_serial_choices(self):
        dialog = self.make()
        self.serials.reset_mock()
        dialog.findChild(QFrame, "levelSeg").findChildren(QPushButton)[0].click()
        self.serials.assert_called_with("carton")

    def test_confirming_exposes_the_reviewed_selection(self):
        dialog = self.make()
        dialog.delete_btn.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual((dialog.level, dialog.serial()), ("display", "D1"))
        self.assertEqual(dialog.preview(), PREVIEW)


class FakeDialog:
    """Stands in for the modal DeleteContainerDialog, which cannot be driven by exec()."""
    instances = []
    outcome = QDialog.Accepted

    def __init__(self, parent=None, **kwargs):
        self.kwargs = kwargs
        self.level = "display"
        FakeDialog.instances.append(self)

    def exec(self):
        return FakeDialog.outcome

    def serial(self):
        return "D1"

    def preview(self):
        return PREVIEW


class FakeMenu:
    pick = 1

    def __init__(self, parent=None):
        self.labels, self.actions = [], []

    def addAction(self, label):
        action = object()
        self.labels.append(str(label))
        self.actions.append(action)
        return action

    def exec(self, pos):
        return self.actions[FakeMenu.pick]


class DeleteContainerFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # A non-default table, so code that falls back to the hard-coded name is caught.
        patch("main_window.STAGING_TABLE", "fpl_test").start()
        patch("db.get_columns", return_value=[]).start()
        patch("db.fetch_distinct_values", return_value=[]).start()
        FakeDialog.instances, FakeDialog.outcome = [], QDialog.Accepted
        patch("main_window.DeleteContainerDialog", FakeDialog).start()
        self.ask = patch("main_window.QMessageBox.question",
                         return_value=QMessageBox.Yes).start()
        self.delete = patch("db.delete_container", return_value=dict(DELETED)).start()
        self.win = MainWindow("tester", "admin", "TEST-OPERATOR")
        self.search = patch.object(self.win, "_on_search").start()

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()
        patch.stopall()

    def test_a_confirmed_delete_uses_the_configured_table_the_tag_and_the_reviewed_counts(self):
        self.win._delete_container()
        self.delete.assert_called_once_with(
            "display", "D1", table="fpl_test", tag_name="TEST-OPERATOR", expected=PREVIEW)
        self.search.assert_called_once()
        self.assertRegex(self.win.status_label.text(), r"\b2\b.*\b3\b")

    def test_the_final_question_states_the_blast_radius_and_defaults_to_no(self):
        self.win._delete_container()
        args = self.ask.call_args.args
        self.assertRegex(str(args[2]), r"\b2\b.*\b3\b")
        self.assertIn("I1", str(args[2]))
        self.assertIn("public.fpl_test", str(args[2]))
        self.assertEqual(args[4], QMessageBox.No)

    def test_declining_the_final_question_deletes_nothing(self):
        self.ask.return_value = QMessageBox.No
        self.win._delete_container()
        self.delete.assert_not_called()
        self.search.assert_not_called()

    def test_cancelling_the_dialog_deletes_nothing(self):
        FakeDialog.outcome = QDialog.Rejected
        self.win._delete_container()
        self.ask.assert_not_called()
        self.delete.assert_not_called()

    def test_the_dialog_is_given_the_configured_table_and_any_preselection(self):
        self.win._delete_container("inner", "I1")
        kwargs = FakeDialog.instances[0].kwargs
        self.assertEqual((kwargs["table"], kwargs["level"], kwargs["serial"]),
                         ("fpl_test", "inner", "I1"))

    def test_non_admins_cannot_open_the_dialog(self):
        self.win.is_admin = False
        self.win._delete_container()
        self.assertEqual(FakeDialog.instances, [])

    def test_unsaved_grid_edits_block_the_delete(self):
        self.win._populate_table(["id", "unit_serial_no"], [(1, "U1")], ["id"])
        self.win.table.item(0, 0).setCheckState(Qt.Checked)
        self.win._delete_container()
        self.assertEqual(FakeDialog.instances, [])
        self.assertEqual(self.win.status_label.property("state"), "error")

    def test_a_refused_delete_is_shown_and_the_grid_is_left_alone(self):
        self.delete.side_effect = db.ContainerDeleteError("changed since you looked")
        self.win._delete_container()
        self.assertIn("changed since you looked", self.win.status_label.text())
        self.assertEqual(self.win.status_label.property("state"), "error")
        self.search.assert_not_called()

    def test_an_unreachable_database_is_reported_not_raised(self):
        self.delete.side_effect = psycopg2.OperationalError("down")
        self.win._delete_container()
        self.assertEqual(self.win.status_label.property("state"), "error")

    def test_a_successful_delete_is_noted_in_the_log(self):
        before = len(LOG.entries)
        self.win._delete_container()
        entry = LOG.entries[-1]
        self.assertEqual(len(LOG.entries), before + 1)
        self.assertEqual(entry["level"], "INFO")
        self.assertIn("D1", entry["message"])

    def test_footer_button_and_manager_card_open_the_same_flow(self):
        self.win.delete_container_btn.click()
        self.assertEqual(FakeDialog.instances[-1].kwargs["serial"], "")
        self.win.container_panel.delete_requested.emit("display", "D9")
        self.assertEqual(FakeDialog.instances[-1].kwargs["serial"], "D9")
        self.assertEqual(len(FakeDialog.instances), 2)

    def test_the_footer_button_is_admin_only(self):
        self.assertTrue(self.win.delete_container_btn.isEnabled())
        viewer = MainWindow("viewer", "user", "TAG")
        self.addCleanup(viewer.deleteLater)
        self.assertFalse(viewer.delete_container_btn.isEnabled())

    def test_right_click_on_a_container_cell_offers_delete_after_rename(self):
        self.win._populate_table(["id", "display_serial_no"], [(1, "D1")], ["id"])
        item = self.win.table.item(0, 2)
        with patch.object(self.win.table, "itemAt", return_value=item), \
                patch("main_window.QMenu", FakeMenu), \
                patch.object(self.win, "_rename_container") as rename:
            FakeMenu.pick = 1
            self.win._on_table_context_menu(item.tableWidget().rect().center())
            self.assertEqual(FakeDialog.instances[-1].kwargs["serial"], "D1")
            self.assertEqual(FakeDialog.instances[-1].kwargs["level"], "display")
            rename.assert_not_called()
            FakeMenu.pick = 0
            self.win._on_table_context_menu(item.tableWidget().rect().center())
            rename.assert_called_once_with("display", "D1")


GROUPS = [("C1", "I1", "D1", "U1", 2), ("C1", "I1", "D1", "U2", 1),
          (None, None, "D3", "U3", 1)]


class CardDeleteLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def delete_links(self, card):
        return [button for button in card.findChildren(QPushButton, "linkBtn")
                if button.property("action") == "delete"]

    def test_a_card_requests_the_delete_of_its_own_level_and_serial(self):
        panel = ContainerPanel(True)
        panel.set_groups(GROUPS)
        requested = []
        panel.delete_requested.connect(lambda *args: requested.append(args))
        for path, level, serial in [((), "carton", "C1"), (("C1",), "inner", "I1"),
                                    (("C1", "I1"), "display", "D1")]:
            panel.navigate(path)
            (link,) = self.delete_links(panel.cards[0])
            self.assertTrue(link.isEnabled())
            link.click()
            self.assertEqual(requested[-1], (level, serial))
        panel.deleteLater()

    def test_units_are_deleted_from_the_records_tab_so_their_cards_have_no_link(self):
        panel = ContainerPanel(True)
        panel.set_groups(GROUPS)
        panel.navigate(("C1", "I1", "D1"))
        self.assertEqual(self.delete_links(panel.cards[0]), [])
        panel.deleteLater()

    def test_the_link_is_off_for_non_admins_and_for_groups_without_a_serial(self):
        viewer = ContainerPanel(False)
        viewer.set_groups(GROUPS)
        self.assertFalse(self.delete_links(viewer.cards[0])[0].isEnabled())
        viewer.deleteLater()
        admin = ContainerPanel(True)
        admin.set_groups(GROUPS)
        unassigned = admin.cards[-1]
        self.assertFalse(self.delete_links(unassigned)[0].isEnabled())
        admin.deleteLater()


if __name__ == "__main__":
    unittest.main()
