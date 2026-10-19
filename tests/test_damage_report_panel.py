"""damage_report_panel.DamageReportPanel: the minimal Report damage tab.

Reporting itself is db.report_damage's job (see tests/test_damage_report.py);
this only covers how the panel reacts to each of that function's outcomes.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from unittest.mock import patch

import psycopg2
from PySide6.QtWidgets import QApplication

import db
from damage_report_panel import DamageReportPanel
from i18n import language
from i18n_widgets import QMessageBox


class DamageReportPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # The panel renders through tr(), so it must not depend on whatever
        # language this machine's real app settings last saved.
        saved = language.code
        settings = patch("i18n.QSettings")
        settings.start()
        self.addCleanup(settings.stop)
        self.addCleanup(language.set, saved)
        language.set("en")

    def test_reporting_an_inactive_serial_clears_the_field_and_shows_success(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText(" U1 ")
        with patch("db.report_damage", return_value={"serial_no": "U1", "roll_no": "R1"}) as report:
            panel.report_btn.click()
        report.assert_called_once_with("U1")  # trimmed before the call
        self.assertEqual(panel.serial_edit.text(), "")
        self.assertIn("U1", panel.result_label.text())
        self.assertEqual(panel.result_label.property("state"), "ok")
        panel.deleteLater()

    def test_an_unknown_serial_shows_the_error_and_keeps_the_text(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText("GHOST")
        with patch("db.report_damage", side_effect=db.SerialInventoryError('No serial "GHOST" found.')):
            panel.report_btn.click()
        self.assertIn("GHOST", panel.result_label.text())
        self.assertEqual(panel.result_label.property("state"), "error")
        self.assertEqual(panel.serial_edit.text(), "GHOST")
        panel.deleteLater()

    def test_a_database_outage_shows_a_friendly_message(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText("U1")
        with patch("db.report_damage", side_effect=psycopg2.OperationalError("no route to host")):
            panel.report_btn.click()
        self.assertIn("reach the database", panel.result_label.text().lower())
        panel.deleteLater()

    def test_an_empty_serial_does_nothing(self):
        panel = DamageReportPanel()
        with patch("db.report_damage") as report:
            panel.report_btn.click()
        report.assert_not_called()
        panel.deleteLater()

    def test_a_still_active_serial_offers_to_route_and_emits_on_yes(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText("U1")
        routed = []
        panel.locate_requested.connect(routed.append)
        with patch("db.report_damage", side_effect=db.SerialInUseError('"U1" is still active.')), \
                patch("damage_report_panel.QMessageBox.question", return_value=QMessageBox.Yes) as ask:
            panel.report_btn.click()
        ask.assert_called_once()
        self.assertEqual(routed, ["U1"])
        self.assertEqual(panel.result_label.property("state"), "error")
        panel.deleteLater()

    def test_declining_the_route_does_not_emit(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText("U1")
        routed = []
        panel.locate_requested.connect(routed.append)
        with patch("db.report_damage", side_effect=db.SerialInUseError('"U1" is still active.')), \
                patch("damage_report_panel.QMessageBox.question", return_value=QMessageBox.No):
            panel.report_btn.click()
        self.assertEqual(routed, [])
        panel.deleteLater()

    def test_return_pressed_reports_the_same_as_the_button(self):
        panel = DamageReportPanel()
        panel.serial_edit.setText("U1")
        with patch("db.report_damage", return_value={"serial_no": "U1", "roll_no": "R1"}) as report:
            panel.serial_edit.returnPressed.emit()
        report.assert_called_once_with("U1")
        panel.deleteLater()


class ExportTests(unittest.TestCase):
    ROWS = [{"serial_no": "U1", "level": "Qr Code", "roll_no": "R1", "box_no": "B1",
             "damaged_at": None, "last_user": "VM001"}]

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        saved = language.code
        settings = patch("i18n.QSettings")
        settings.start()
        self.addCleanup(settings.stop)
        self.addCleanup(language.set, saved)
        language.set("en")
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _panel(self):
        panel = DamageReportPanel()
        panel.folder_edit.setText(self.dir.name)
        return panel

    def _export(self, panel, rows=None):
        with patch("db.list_damaged", return_value=self.ROWS if rows is None else rows) as listed, \
                patch("damage_report_pdf.export_pdf") as export, \
                patch("audit_log.record") as audit:
            panel.export_btn.click()
        return listed, export, audit

    def _set_range(self, panel, start, end):
        from PySide6.QtCore import QDateTime
        panel.any_time_check.setChecked(False)
        fmt = "yyyy-MM-dd HH:mm"
        panel.from_edit.setDateTime(QDateTime.fromString(start, fmt))
        panel.to_edit.setDateTime(QDateTime.fromString(end, fmt))

    def test_any_time_is_the_default_and_disables_the_range_editors(self):
        panel = DamageReportPanel()
        self.assertTrue(panel.any_time_check.isChecked())
        self.assertFalse(panel.from_edit.isEnabled() or panel.to_edit.isEnabled())
        panel.any_time_check.setChecked(False)
        self.assertTrue(panel.from_edit.isEnabled() and panel.to_edit.isEnabled())
        panel.deleteLater()

    def test_any_time_exports_without_a_range_and_audits_it(self):
        panel = self._panel()
        listed, export, audit = self._export(panel)
        listed.assert_called_once_with(None, None)
        export.assert_called_once()
        path, rows = export.call_args.args[:2]
        self.assertEqual(os.path.dirname(path), self.dir.name)
        self.assertTrue(os.path.basename(path).startswith("damage_report_"))
        self.assertEqual(rows, self.ROWS)
        self.assertEqual(export.call_args.kwargs["columns"], {"level", "roll_no", "box_no"})
        self.assertIn("1 serial(s)", audit.call_args.args[0])
        self.assertIn(os.path.basename(path), audit.call_args.args[0])
        self.assertEqual(panel.export_result_label.property("state"), "ok")
        panel.deleteLater()

    def test_the_folder_defaults_to_damage_report_dir(self):
        with patch.dict(os.environ, {"DAMAGE_REPORT_DIR": self.dir.name}):
            panel = DamageReportPanel()
        self.assertEqual(panel.folder_edit.text(), self.dir.name)
        panel.deleteLater()

    def test_browse_replaces_the_folder_and_cancel_keeps_it(self):
        panel = self._panel()
        other = os.path.join(self.dir.name, "sub")
        os.mkdir(other)
        with patch("damage_report_panel.QFileDialog.getExistingDirectory", return_value=other):
            panel.browse_btn.click()
        self.assertEqual(panel.folder_edit.text(), os.path.normpath(other))
        with patch("damage_report_panel.QFileDialog.getExistingDirectory", return_value=""):
            panel.browse_btn.click()
        self.assertEqual(panel.folder_edit.text(), os.path.normpath(other))
        panel.deleteLater()

    def test_unticked_columns_are_passed_to_the_pdf(self):
        panel = self._panel()
        panel.column_checks["level"].setChecked(False)
        panel.column_checks["box_no"].setChecked(False)
        _, export, _ = self._export(panel)
        self.assertEqual(export.call_args.kwargs["columns"], {"roll_no"})
        panel.deleteLater()

    def test_a_missing_folder_is_refused_before_any_query(self):
        panel = self._panel()
        panel.folder_edit.setText(os.path.join(self.dir.name, "nope"))
        listed, export, _ = self._export(panel)
        listed.assert_not_called()
        export.assert_not_called()
        self.assertIn("Folder does not exist", panel.export_result_label.text())
        panel.deleteLater()

    def test_a_chosen_range_is_passed_to_the_query_as_aware_datetimes(self):
        panel = self._panel()
        self._set_range(panel, "2026-10-01 08:00", "2026-10-02 17:30")
        listed, *_ = self._export(panel)
        start, end = listed.call_args.args
        self.assertIsNotNone(start.tzinfo)
        self.assertEqual((start.day, start.hour, start.minute), (1, 8, 0))
        # The end minute is inclusive: 17:30 means up to 17:30:59.
        self.assertEqual((end.day, end.hour, end.minute, end.second), (2, 17, 30, 59))
        panel.deleteLater()

    def test_a_backwards_range_is_refused_before_any_query(self):
        panel = self._panel()
        self._set_range(panel, "2026-10-05 08:00", "2026-10-01 08:00")
        listed, export, _ = self._export(panel)
        listed.assert_not_called()
        export.assert_not_called()
        self.assertEqual(panel.export_result_label.property("state"), "error")
        panel.deleteLater()

    def test_nothing_damaged_in_range_says_so_and_writes_no_file(self):
        panel = self._panel()
        _, export, _ = self._export(panel, rows=[])
        export.assert_not_called()
        self.assertIn("No damaged serials", panel.export_result_label.text())
        panel.deleteLater()

    def test_a_database_outage_and_a_write_failure_show_errors(self):
        panel = self._panel()
        with patch("db.list_damaged", side_effect=psycopg2.OperationalError("down")):
            panel.export_btn.click()
        self.assertEqual(panel.export_result_label.property("state"), "error")
        self.assertTrue(panel.export_btn.isEnabled())  # not left disabled
        with patch("db.list_damaged", return_value=self.ROWS), \
                patch("damage_report_pdf.export_pdf", side_effect=PermissionError("locked")), \
                patch("audit_log.record") as audit:
            panel.export_btn.click()
        self.assertEqual(panel.export_result_label.property("state"), "error")
        self.assertIn("locked", panel.export_result_label.text())
        audit.assert_not_called()  # a failed export is not an activity
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
