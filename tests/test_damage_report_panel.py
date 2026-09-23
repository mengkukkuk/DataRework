"""damage_report_panel.DamageReportPanel: the minimal Report damage tab.

Reporting itself is db.report_damage's job (see tests/test_damage_report.py);
this only covers how the panel reacts to each of that function's outcomes.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


if __name__ == "__main__":
    unittest.main()
