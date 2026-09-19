import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from rename_dialog import RenameContainerDialog


class BarcodeRenameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch('db.container_serials', return_value=['C-FIRST', 'C-SCANNED'])
    @patch('db.container_rename_preview', return_value={'rows': 3, 'edges': 2})
    def test_keyboard_scanner_focus_and_enter_never_submit(self, preview, serials):
        dialog = RenameContainerDialog(scan_ready=True)
        accepted = []
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.show()
        self.app.processEvents()
        old = dialog.old_combo.lineEdit()
        self.assertTrue(old.hasFocus())
        self.assertEqual(dialog.values(), ('', ''))
        preview.reset_mock()
        QTest.keyClicks(old, 'C-SCANNED')
        preview.assert_not_called()
        QTest.keyClick(old, Qt.Key_Return)
        self.assertEqual(dialog.values(), ('C-SCANNED', 'C-SCANNED'))
        self.assertTrue(dialog.new_edit.hasFocus())
        self.assertEqual(dialog.new_edit.selectedText(), 'C-SCANNED')
        QTest.keyClicks(dialog.new_edit, 'C-NEW')
        QTest.keyClick(dialog.new_edit, Qt.Key_Return)
        QTest.keyClick(dialog.new_edit, Qt.Key_Enter)
        self.assertEqual(dialog.values(), ('C-SCANNED', 'C-NEW'))
        self.assertEqual(accepted, [])
        self.assertTrue(dialog.confirm_btn.isEnabled())
        dialog.confirm_btn.click()
        self.assertEqual(accepted, [True])
        dialog.deleteLater()

    @patch('db.container_serials', return_value=['C1'])
    @patch('db.container_rename_preview', return_value={'rows': 1, 'edges': 1})
    def test_card_prefill_focuses_replacement(self, *mocks):
        dialog = RenameContainerDialog(serial='C1')
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.new_edit.hasFocus())
        self.assertEqual(dialog.new_edit.selectedText(), 'C1')
        dialog.close()
        dialog.deleteLater()
