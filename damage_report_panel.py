"""Report one serial as damaged.

Deliberately minimal: one field, one button. Everything else an operator
might need first -- browsing, renaming, deleting -- already lives in the
other tabs; this one only ever flips staging_serial_data.is_damaged, and
only once the serial is confirmed out of active use (see db.report_damage).
"""
import os

import psycopg2
from PySide6.QtCore import QDate, QDateTime, QTime, Signal
from PySide6.QtWidgets import (QDateTimeEdit, QFileDialog, QHBoxLayout, QSizePolicy,
                               QVBoxLayout)

import audit_log
import damage_report_pdf
import db
from i18n import tr
from i18n_widgets import (QCheckBox, QLabel, QLineEdit, QMessageBox, QPushButton,
                          QWidget)

DATETIME_FORMAT = "yyyy-MM-dd HH:mm"


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

        # --- Export: a PDF of the serials that are damaged right now ----------
        layout.addSpacing(18)
        export_title = QLabel(tr("Export damage report"))
        export_title.setObjectName("dialogTitle")
        layout.addWidget(export_title)
        export_hint = QLabel(tr(
            "Save a PDF listing the serials that are damaged right now. Untick "
            "Any time to list only those reported damaged within a time range."
        ))
        export_hint.setObjectName("dialogHint")
        export_hint.setWordWrap(True)
        layout.addWidget(export_hint)

        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        self.any_time_check = QCheckBox(tr("Any time"))
        self.any_time_check.setChecked(True)
        self.any_time_check.toggled.connect(self._on_any_time_toggled)
        export_row.addWidget(self.any_time_check)
        today = QDate.currentDate()
        self.from_edit = self._datetime_edit(QDateTime(today, QTime(0, 0)))
        self.to_edit = self._datetime_edit(QDateTime(today, QTime(23, 59)))
        self.from_label = QLabel(tr("From"))
        self.to_label = QLabel(tr("To"))
        for widget in (self.from_label, self.from_edit, self.to_label, self.to_edit):
            export_row.addWidget(widget)
        export_row.addStretch(1)
        layout.addLayout(export_row)
        self._on_any_time_toggled(True)

        # --- Export: as datetime-damage-report.txt (Only serial no. in selected time range in report) -----------------------------
        
        
        columns_row = QHBoxLayout()
        columns_row.setSpacing(8)
        columns_row.addWidget(QLabel(tr("Columns")))
        self.column_checks = {}
        for key, heading in damage_report_pdf.OPTIONAL_COLUMNS:
            check = QCheckBox(tr(heading))
            check.setChecked(True)
            self.column_checks[key] = check
            columns_row.addWidget(check)
        columns_row.addStretch(1)
        layout.addLayout(columns_row)

        # The folder starts at DAMAGE_REPORT_DIR (.env); the file name is dated.
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_row.addWidget(QLabel(tr("Save to")))
        self.folder_edit = QLineEdit(damage_report_pdf.default_folder())
        self.folder_edit.setObjectName("damageReportFolder")
        self.folder_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        folder_row.addWidget(self.folder_edit, 1)

        #section button
        self.browse_btn = QPushButton(tr("Browse..."))
        self.browse_btn.setObjectName("ghostBtn")
        self.browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self.browse_btn)
        #open folder button open_browse_folder
        self.open_folder_btn = QPushButton(tr("Open folder"))
        self.open_folder_btn.setObjectName("ghostBtn")
        self.open_folder_btn.clicked.connect(self._on_open_browse_folder)
        folder_row.addWidget(self.open_folder_btn)
        """self.export_btn = QPushButton(tr("Export PDF"))
        self.export_btn.setObjectName("ghostBtn")
        self.export_btn.clicked.connect(self._on_export)
        folder_row.addWidget(self.export_btn)"""
        self.export_txt_btn = QPushButton(tr("Export TXT"))
        self.export_txt_btn.setObjectName("ghostBtn")
        self.export_txt_btn.clicked.connect(self._on_export_txt)
        folder_row.addWidget(self.export_txt_btn)
        layout.addLayout(folder_row)

        self.export_result_label = QLabel("")
        self.export_result_label.setObjectName("statusLabel")
        self.export_result_label.setWordWrap(True)
        layout.addWidget(self.export_result_label)
        layout.addStretch(1)

    @staticmethod
    def _datetime_edit(value):
        edit = QDateTimeEdit(value)
        edit.setDisplayFormat(DATETIME_FORMAT)
        edit.setCalendarPopup(True)
        return edit

    def focus_input(self):
        self.serial_edit.setFocus()
        self.serial_edit.selectAll()

    def _set_result(self, text, error=False, label=None):
        label = label or self.result_label
        label.setText(text)
        label.setProperty("state", "error" if error else "ok")
        label.style().unpolish(label)
        label.style().polish(label)

    def _on_any_time_toggled(self, any_time):
        for widget in (self.from_label, self.from_edit, self.to_label, self.to_edit):
            widget.setEnabled(not any_time)

    def _selected_range(self):
        """(start, end) as timezone-aware datetimes, or (None, None) for any time."""
        if self.any_time_check.isChecked():
            return None, None
        # The editors show local wall-clock time; astimezone() on a naive value
        # reads it as local, so the database compares the same instant.
        start = self.from_edit.dateTime().toPython().astimezone()
        end = self.to_edit.dateTime().toPython().astimezone().replace(second=59)
        return start, end

    def selected_columns(self):
        return {key for key, check in self.column_checks.items() if check.isChecked()}

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, str(tr("Choose where to save the report")), self.folder_edit.text().strip())
        if folder:
            self.folder_edit.setText(os.path.normpath(folder))

    def _on_export(self):
        label = self.export_result_label
        start, end = self._selected_range()
        if start is not None and start > end:
            self._set_result(tr("The start of the range is after its end."), error=True, label=label)
            return
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            self._set_result(tr("Folder does not exist: {p0}", p0=folder), error=True, label=label)
            return
        self.export_btn.setEnabled(False)
        try:
            rows = db.list_damaged(start, end)
        except psycopg2.OperationalError:
            self._set_result(tr("Unable to reach the database"), error=True, label=label)
            return
        except Exception as exc:
            self._set_result(tr("Export failed: {p0}", p0=exc), error=True, label=label)
            return
        finally:
            self.export_btn.setEnabled(True)

        if not rows:
            self._set_result(tr("No damaged serials in this range."), label=label)
            return
        path = os.path.join(folder, damage_report_pdf.default_filename())
        try:
            damage_report_pdf.export_pdf(
                path, rows, start, end, generated_by=audit_log.session_tag(),
                vm_id=os.environ.get("VM_ID", "").strip(), columns=self.selected_columns())
        except OSError as exc:
            self._set_result(tr("Export failed: {p0}", p0=exc), error=True, label=label)
            return
        audit_log.record(
            f"Export damage report - {len(rows)} serial(s), "
            f"{damage_report_pdf.describe_range(start, end)}, file {os.path.basename(path)}")

    def _on_export_txt(self):
        label = self.export_result_label
        start, end = self._selected_range()
        if start is not None and start > end:
            self._set_result(tr("The start of the range is after its end."), error=True, label=label)
            return
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            self._set_result(tr("Folder does not exist: {p0}", p0=folder), error=True, label=label)
            return
        self.export_txt_btn.setEnabled(False)
        try:
            rows = db.list_damaged(start, end)
        except psycopg2.OperationalError:
            self._set_result(tr("Unable to reach the database"), error=True, label=label)
            return
        except Exception as exc:
            self._set_result(tr("Export failed: {p0}", p0=exc), error=True, label=label)
            return
        finally:
            self.export_txt_btn.setEnabled(True)

        if not rows:
            self._set_result(tr("No damaged serials in this range."), label=label)
            return
        path = os.path.join(folder,
                            f"datetime-damage-report-{QDateTime.currentDateTime().toString('yyyyMMddHHmmss')}.txt")
        try:
            with open(path, "w", encoding="utf-8") as txt_file:
                txt_file.writelines(f"{row['serial_no']}\n" for row in rows)
        except OSError as exc:
            self._set_result(tr("Export failed: {p0}", p0=exc), error=True, label=label)
            return
        audit_log.record(
            f"Export TXT damage report - {len(rows)} serial(s), "
            f"{damage_report_pdf.describe_range(start, end)}, file {os.path.basename(path)}")
        self._set_result(
            tr("Exported {p0} damaged serial(s) to {p1}", p0=len(rows), p1=path), label=label)
        self._set_result(
            tr("Exported {p0} damaged serial(s) to {p1}", p0=len(rows), p1=path), label=label)

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
            audit_log.record(
                f'Report damage - serial "{result["serial_no"]}" (roll {result["roll_no"]})')
            self._set_result(tr('Reported "{p0}" damaged.', p0=result["serial_no"]))
            self.serial_edit.clear()
        finally:
            self.report_btn.setEnabled(True)
            self.focus_input()

    def _on_open_browse_folder(self):
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            return
        os.startfile(folder)

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
