"""Report one serial as damaged.

Deliberately minimal: one field, one button. Everything else an operator
might need first -- browsing, renaming, deleting -- already lives in the
other tabs; this one only ever flips staging_serial_data.is_damaged, and
only once the serial is confirmed out of active use (see db.report_damage).
"""
import psycopg2
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout

import db
from i18n import tr
from i18n_widgets import QLabel, QLineEdit, QMessageBox, QPushButton, QWidget


class DamageReportPanel(QWidget):
    # Emitted when the operator agrees to go take a still-active serial out
    # of use before reporting it damaged; MainWindow owns the other tabs, so
    # it is the one that acts on this.
    locate_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("damagePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        title = QLabel(tr("Report damage"))
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        hint = QLabel(tr(
            "Scan or type a serial number -- unit, display, inner or carton -- "
            "to flag it damaged. Only a serial that is not currently in use "
            "can be reported."
        ))
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.serial_edit = QLineEdit()
        self.serial_edit.setObjectName("damageSerial")
        self.serial_edit.setPlaceholderText(tr("Scan or type the damaged serial"))
        self.serial_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.serial_edit.returnPressed.connect(self._on_report)
        row.addWidget(self.serial_edit, 1)

        self.report_btn = QPushButton(tr("Report damage"))
        self.report_btn.setObjectName("deleteBtn")
        self.report_btn.clicked.connect(self._on_report)
        row.addWidget(self.report_btn)
        layout.addLayout(row)

        self.result_label = QLabel("")
        self.result_label.setObjectName("statusLabel")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        layout.addStretch(1)

    def focus_input(self):
        self.serial_edit.setFocus()
        self.serial_edit.selectAll()

    def _set_result(self, text, error=False):
        self.result_label.setText(text)
        self.result_label.setProperty("state", "error" if error else "ok")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)

    def _on_report(self):
        serial = self.serial_edit.text().strip()
        if not serial:
            return
        self.report_btn.setEnabled(False)
        try:
            result = db.report_damage(serial)
        except db.SerialInUseError:
            self._offer_route(serial)
        except psycopg2.OperationalError:
            self._set_result(tr("Unable to reach the database"), error=True)
        except (db.SerialInventoryError, ValueError) as exc:
            self._set_result(str(exc), error=True)
        except Exception as exc:
            self._set_result(str(exc), error=True)
        else:
            self._set_result(tr('Reported "{p0}" damaged.', p0=result["serial_no"]))
            self.serial_edit.clear()
        finally:
            self.report_btn.setEnabled(True)
            self.focus_input()

    def _offer_route(self, serial):
        reply = QMessageBox.question(
            self,
            tr("Serial in use"),
            tr(
                '"{p0}" is still in use, so it cannot be reported damaged yet. '
                "Open it in the records editor to take it out of use first?",
                p0=serial,
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.locate_requested.emit(serial)
        self._set_result(
            tr('"{p0}" is still in use -- take it out of use, then report it again.', p0=serial),
            error=True,
        )
