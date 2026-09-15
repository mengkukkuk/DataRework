import datetime
import os
import tempfile

import psycopg2
from psycopg2 import sql
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import db

# --- Schema mapping --------------------------------------------------------
# public.staging_product_logs is looked up dynamically (columns, primary key)
# so the table's real shape is never hardcoded. The names below only map the
# *filter fields* to the columns they query.
#
# NOTE: staging_product_logs has both `assignment_no` and `job_no`. The
# "Assignment job no." filter is wired to `assignment_no` — swap to "job_no"
# below if that's not the intended field.
STAGING_TABLE = "staging_product_logs"
DATE_COLUMN = "create_date"
FILTER_COLUMNS = {
    "line": "vm_line",
    "assignment_no": "assignment_no",
    "parent_no": "parent_serial_no",
    "serial_no": "serial_no",
}

# Order the typing-combo filters cascade in: each one's dropdown is scoped to
# values that actually occur given the month/year plus every field before it
# here, so e.g. picking a job no. narrows what parent/serial no. can be.
CASCADE_FIELDS = ["line", "assignment_no", "parent_no", "serial_no"]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _generate_dropdown_arrow_icon():
    """A small solid down-triangle PNG for QComboBox's drop-down arrow.
    Qt's QSS doesn't render the usual CSS border-triangle trick as a
    triangle (it just paints a filled block), so this draws one directly."""
    path = os.path.join(tempfile.gettempdir(), "datarework_combo_arrow.png")
    if not os.path.exists(path):
        image = QImage(20, 20, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#8fa5bf"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(4, 7), QPointF(16, 7), QPointF(10, 14)]))
        painter.end()
        image.save(path)
    return path.replace("\\", "/")

STYLE_SHEET = """
QMainWindow, #central {
    background-color: #0a0e14;
}
QLabel {
    color: #c7d3e0;
    font-size: 13px;
}
#pageTitle {
    color: #f2f6fb;
    font-size: 21px;
    font-weight: 600;
}
#pageSubtitle {
    color: #5d7086;
    font-size: 12px;
}
#userBadge {
    color: #9fb4cc;
    font-size: 12px;
    background-color: #101826;
    border: 1px solid #1f2c3f;
    border-radius: 11px;
    padding: 5px 14px;
}
#userBadge[admin="true"] {
    color: #8fe3ab;
    border: 1px solid #1f4a33;
}
QGroupBox {
    background-color: #101722;
    border: 1px solid #1c2636;
    border-radius: 10px;
    margin-top: 6px;
    padding: 16px 14px 14px 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #6f88a6;
    font-size: 11px;
    font-weight: 700;
}
QComboBox {
    background-color: #16273d;
    color: #eaf1fa;
    border: 1px solid #24405e;
    border-radius: 6px;
    padding: 7px 10px;
    min-width: 108px;
    font-size: 13px;
}
QComboBox:hover {
    border: 1px solid #3a6690;
}
QComboBox:focus {
    border: 1px solid #5b9bd5;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: url(__DROPDOWN_ARROW_ICON__);
    width: 10px;
    height: 10px;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #16273d;
    color: #eaf1fa;
    selection-background-color: #274a6e;
    border: 1px solid #24405e;
    outline: none;
}
QPushButton {
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
    color: #08111d;
}
#searchBtn { background-color: #5b9bd5; color: #06131f; }
#searchBtn:hover { background-color: #75b0e0; }
#clearBtn { background-color: #2a3a4f; color: #cddbea; }
#clearBtn:hover { background-color: #37516f; }
#saveBtn { background-color: #3fae72; color: #05170e; }
#saveBtn:hover { background-color: #57c187; }
#saveBtn:disabled { background-color: #223228; color: #4c5c52; }
#cancelBtn { background-color: #e2a0b3; color: #2a0d15; }
#cancelBtn:hover { background-color: #eab2c2; }
#columnsStrip {
    background-color: #0d131d;
    border: 1px solid #1c2636;
    border-radius: 8px;
}
#columnsStrip QScrollArea, #columnsStrip QScrollArea > QWidget > QWidget, #columnsStrip QWidget#columnsStripInner {
    background-color: transparent;
    border: none;
}
QCheckBox {
    color: #b6c4d6;
    font-size: 12px;
    spacing: 6px;
    padding: 2px 4px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #3a4d66;
    background-color: #16273d;
}
QCheckBox::indicator:checked {
    background-color: #5b9bd5;
    border: 1px solid #5b9bd5;
}
QTableWidget {
    background-color: #0d131d;
    alternate-background-color: #111a27;
    color: #dde6f0;
    gridline-color: #1c2636;
    border: 1px solid #1c2636;
    border-radius: 8px;
    selection-background-color: #274a6e;
    selection-color: #ffffff;
    font-size: 12px;
}
QTableWidget::item {
    padding: 4px 6px;
}
QHeaderView::section {
    background-color: #141d2c;
    color: #8fa5bf;
    border: none;
    border-bottom: 2px solid #24405e;
    padding: 7px 6px;
    font-size: 11px;
    font-weight: 700;
}
#statusLabel[state="error"] { color: #e2879d; }
#statusLabel[state="ok"] { color: #7fd6a3; }
QScrollBar:vertical, QScrollBar:horizontal {
    background: #0d131d;
    width: 10px;
    height: 10px;
}
QScrollBar::handle {
    background: #24405e;
    border-radius: 5px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self, username, permission):
        super().__init__()
        self.username = username
        self.permission = permission
        self.is_admin = permission == "admin"

        self._columns = []
        self._pk_columns = []
        self._row_pks = []
        self._row_originals = []
        self._show_delete_col = False
        self._column_checks = {}

        self.setWindowTitle("Production Rework")
        self.resize(1300, 700)
        arrow_icon_path = _generate_dropdown_arrow_icon()
        self.setStyleSheet(STYLE_SHEET.replace("__DROPDOWN_ARROW_ICON__", arrow_icon_path))

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_columns_strip())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_footer())

        self._refresh_dependent_combos()

    # -- construction ------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Production Rework")
        title.setObjectName("pageTitle")
        subtitle = QLabel(f"Table = {STAGING_TABLE}")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addLayout(title_box)
        row.addStretch(1)

        badge = QLabel(f"{self.username}  ·  {self.permission}")
        badge.setObjectName("userBadge")
        badge.setProperty("admin", "true" if self.is_admin else "false")
        row.addWidget(badge, alignment=Qt.AlignVCenter)
        return row

    def _build_filter_bar(self):
        group = QGroupBox("Filters")
        layout = QHBoxLayout(group)
        layout.setSpacing(10)

        self.month_combo = QComboBox()
        self.month_combo.addItem("Month", None)
        for i, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(name, i)
        self.month_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.month_combo.setFixedWidth(130)

        self.year_combo = QComboBox()
        self.year_combo.addItem("Year", None)
        current_year = datetime.date.today().year
        for y in range(current_year - 5, current_year + 2):
            self.year_combo.addItem(str(y), y)
        self.year_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.year_combo.setFixedWidth(100)

        today = datetime.date.today()
        self.month_combo.setCurrentIndex(self.month_combo.findData(today.month))
        self.year_combo.setCurrentIndex(self.year_combo.findData(today.year))

        self.line_combo = self._make_typing_combo("Line")
        self.job_combo = self._make_typing_combo("Ass. job no.")
        self.parent_combo = self._make_typing_combo("Parent no.")
        self.serial_combo = self._make_typing_combo("Serial no.")
        self._cascade_combos = {
            "line": self.line_combo,
            "assignment_no": self.job_combo,
            "parent_no": self.parent_combo,
            "serial_no": self.serial_combo,
        }

        for w in (
            self.month_combo, self.year_combo,
            self.line_combo, self.job_combo, self.parent_combo, self.serial_combo,
        ):
            layout.addWidget(w)

        # Date changes affect every downstream combo; each typing combo only
        # affects the ones after it in CASCADE_FIELDS. Refresh on
        # editingFinished/activated rather than every keystroke, so typing
        # doesn't fire a query per character.
        self.month_combo.currentIndexChanged.connect(lambda _=None: self._refresh_dependent_combos())
        self.year_combo.currentIndexChanged.connect(lambda _=None: self._refresh_dependent_combos())
        for field_key in CASCADE_FIELDS[:-1]:
            combo = self._cascade_combos[field_key]
            combo.lineEdit().editingFinished.connect(
                lambda fk=field_key: self._refresh_dependent_combos(fk)
            )
            combo.activated.connect(
                lambda _=None, fk=field_key: self._refresh_dependent_combos(fk)
            )

        layout.addStretch(1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("searchBtn")
        self.search_btn.clicked.connect(self._on_search)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self._on_clear)

        layout.addWidget(self.clear_btn)
        layout.addWidget(self.search_btn)
        return group

    def _make_typing_combo(self, placeholder):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.lineEdit().setPlaceholderText(placeholder)
        combo.setCurrentText("")
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        combo.setFixedWidth(170)
        return combo

    def _build_columns_strip(self):
        frame = QFrame()
        frame.setObjectName("columnsStrip")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(10, 4, 10, 4)

        label = QLabel("Columns")
        label.setStyleSheet("color:#5d7086; font-size:11px; font-weight:700;")
        outer.addWidget(label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(40)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self._columns_strip_inner = QWidget()
        self._columns_strip_inner.setObjectName("columnsStripInner")
        self._columns_strip_layout = QHBoxLayout(self._columns_strip_inner)
        self._columns_strip_layout.setContentsMargins(4, 4, 4, 4)
        self._columns_strip_layout.addStretch(1)
        scroll.setWidget(self._columns_strip_inner)

        outer.addWidget(scroll, stretch=1)
        return frame

    def _build_table(self):
        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return self.table

    def _build_footer(self):
        row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        row.addWidget(self.status_label)
        row.addStretch(1)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(self.is_admin)
        if not self.is_admin:
            self.save_btn.setToolTip("Only admins can save changes")

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self._on_cancel)

        row.addWidget(self.save_btn)
        row.addWidget(self.cancel_btn)
        return row

    # -- data -------------------------------------------------------------

    def _date_conditions(self, columns):
        conditions = []
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        if (month or year) and DATE_COLUMN in columns:
            if month:
                conditions.append(
                    (sql.SQL("EXTRACT(MONTH FROM {}) = %s").format(sql.Identifier(DATE_COLUMN)), [month])
                )
            if year:
                conditions.append(
                    (sql.SQL("EXTRACT(YEAR FROM {}) = %s").format(sql.Identifier(DATE_COLUMN)), [year])
                )
        return conditions

    def _current_conditions(self, columns, upto=None):
        """WHERE conditions from filters already chosen (date range plus
        cascade fields before `upto`), used to scope a dropdown to values
        that actually occur under everything picked so far."""
        conditions = self._date_conditions(columns)
        for field_key in CASCADE_FIELDS:
            if field_key == upto:
                break
            col = FILTER_COLUMNS.get(field_key)
            value = self._cascade_combos[field_key].currentText().strip()
            if col and col in columns and value:
                conditions.append((sql.SQL("{} = %s").format(sql.Identifier(col)), [value]))
        return conditions

    def _refresh_dependent_combos(self, from_field=None):
        """Repopulate the typing combos after `from_field` in CASCADE_FIELDS
        (all of them if `from_field` is None) with the distinct values that
        actually occur given the date range and every filter before them."""
        try:
            columns = db.get_columns(STAGING_TABLE)
        except Exception as exc:
            print(f"Could not refresh filter choices: {exc}")
            return

        start = 0 if from_field is None else CASCADE_FIELDS.index(from_field) + 1
        for field_key in CASCADE_FIELDS[start:]:
            combo = self._cascade_combos[field_key]
            col = FILTER_COLUMNS.get(field_key)
            if not col or col not in columns:
                continue

            conditions = self._current_conditions(columns, upto=field_key)
            try:
                values = db.fetch_distinct_values(STAGING_TABLE, col, conditions=conditions)
            except Exception as exc:
                print(f"Could not refresh {field_key} choices: {exc}")
                continue

            kept_text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([str(v) for v in values if v is not None])
            combo.setCurrentText(kept_text)
            combo.blockSignals(False)

    def _on_search(self):
        try:
            columns = db.get_columns(STAGING_TABLE)
        except psycopg2.OperationalError:
            self._show_status("Unable to reach the database", error=True)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True)
            return

        if not columns:
            self._show_status(f'Table "public.{STAGING_TABLE}" was not found.', error=True)
            self._reset_table()
            return

        warnings = []
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        if (month or year) and DATE_COLUMN not in columns:
            warnings.append("date filter skipped (no date column)")

        for field_key in CASCADE_FIELDS:
            value = self._cascade_combos[field_key].currentText().strip()
            if value and (FILTER_COLUMNS.get(field_key) not in columns):
                warnings.append(f"{field_key} filter skipped (no such column)")

        conditions = self._current_conditions(columns)

        try:
            pk_columns = db.get_primary_key_columns(STAGING_TABLE)
            col_names, rows = db.query_rows(STAGING_TABLE, columns, conditions)
        except psycopg2.OperationalError:
            self._show_status("Unable to reach the database", error=True)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True)
            return

        self._populate_table(col_names, rows, pk_columns)
        message = f"{len(rows)} row(s) loaded."
        if warnings:
            message += " " + "; ".join(warnings)
            self._show_status(message, error=True)
        else:
            self._show_status(message)

    def _populate_table(self, columns, rows, pk_columns):
        self._columns = columns
        self._pk_columns = pk_columns
        self._show_delete_col = self.is_admin and bool(pk_columns)
        editable = self.is_admin and bool(pk_columns)

        offset = 1 if self._show_delete_col else 0
        self.table.setColumnCount(len(columns) + offset)
        headers = (["Del"] if self._show_delete_col else []) + columns
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))

        self._row_pks = []
        self._row_originals = []

        for r, row_values in enumerate(rows):
            row_dict = dict(zip(columns, row_values))
            pk_values = tuple(row_dict[c] for c in pk_columns) if pk_columns else None
            self._row_pks.append(pk_values)
            self._row_originals.append(row_dict)

            if self._show_delete_col:
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                chk_item.setCheckState(Qt.Unchecked)
                self.table.setItem(r, 0, chk_item)

            for c, col in enumerate(columns):
                value = row_dict[col]
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
                if editable:
                    flags |= Qt.ItemIsEditable
                item.setFlags(flags)
                self.table.setItem(r, c + offset, item)

        self.table.resizeColumnsToContents()
        self._rebuild_columns_strip(columns, offset)

    def _rebuild_columns_strip(self, columns, offset):
        layout = self._columns_strip_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._column_checks = {}
        for idx, col in enumerate(columns):
            cb = QCheckBox(col)
            cb.setChecked(True)
            cb.toggled.connect(lambda checked, i=idx + offset: self.table.setColumnHidden(i, not checked))
            layout.addWidget(cb)
            self._column_checks[col] = cb
        layout.addStretch(1)

    def _reset_table(self):
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._columns = []
        self._pk_columns = []
        self._row_pks = []
        self._row_originals = []
        self._show_delete_col = False
        self._rebuild_columns_strip([], 0)

    # -- actions ------------------------------------------------------------

    def _on_clear(self):
        self.month_combo.blockSignals(True)
        self.year_combo.blockSignals(True)
        self.month_combo.setCurrentIndex(0)
        self.year_combo.setCurrentIndex(0)
        self.month_combo.blockSignals(False)
        self.year_combo.blockSignals(False)
        for combo in (self.line_combo, self.job_combo, self.parent_combo, self.serial_combo):
            combo.setCurrentText("")
        self._refresh_dependent_combos()
        self.status_label.clear()
        self.status_label.setProperty("state", "")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_cancel(self):
        self._on_clear()
        self._reset_table()
        self._show_status("Cleared.")

    def _on_save(self):
        if not self.is_admin:
            self._show_status("Only admins can save changes.", error=True)
            return
        if not self._pk_columns:
            self._show_status("This table has no primary key — nothing can be saved.", error=True)
            return

        updates, deletes = self._collect_changes()
        if not updates and not deletes:
            self._show_status("No changes to save.")
            return

        parts = []
        if updates:
            parts.append(f"update {len(updates)} row(s)")
        if deletes:
            parts.append(f"delete {len(deletes)} row(s)")

        reply = QMessageBox.question(
            self,
            "Confirm changes",
            f"This will {' and '.join(parts)} in public.{STAGING_TABLE}. "
            "This cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            db.save_changes(STAGING_TABLE, self._pk_columns, updates, deletes)
        except psycopg2.OperationalError:
            self._show_status("Unable to reach the database", error=True)
            return
        except Exception as exc:
            self._show_status(f"Save failed: {exc}", error=True)
            return

        self._show_status("Changes saved.")
        self._on_search()

    def _collect_changes(self):
        updates = []
        deletes = []
        offset = 1 if self._show_delete_col else 0

        for r in range(self.table.rowCount()):
            pk_values = self._row_pks[r]
            if pk_values is None:
                continue

            if self._show_delete_col:
                del_item = self.table.item(r, 0)
                if del_item and del_item.checkState() == Qt.Checked:
                    deletes.append(pk_values)
                    continue

            original = self._row_originals[r]
            changes = {}
            for c, col in enumerate(self._columns):
                item = self.table.item(r, c + offset)
                text = item.text() if item else ""
                orig_value = original.get(col)
                orig_text = "" if orig_value is None else str(orig_value)
                if text != orig_text:
                    changes[col] = text if text != "" else None
            if changes:
                updates.append((pk_values, changes))

        return updates, deletes

    def _show_status(self, message, error=False):
        self.status_label.setText(message)
        self.status_label.setProperty("state", "error" if error else "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
