import datetime
import os
import tempfile

import psycopg2
from psycopg2 import sql
from PySide6.QtCore import Qt, QPointF, QSettings
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
# *filter fields* to the columns they query — read from .env (see db.py's
# load_dotenv() call in main.py) so the mapping can be retuned without
# touching code, falling back to the values confirmed against the real
# schema if a var is unset.
STAGING_TABLE = os.environ.get("STAGING_TABLE", "staging_product_logs")
DATE_COLUMN = os.environ.get("DATE_COLUMN", "create_date")
FILTER_COLUMNS = {
    "line": os.environ.get("FILTER_COLUMN_LINE", "vm_line"),
    "assignment_no": os.environ.get("FILTER_COLUMN_ASSIGNMENT_NO", "assignment_no"),
    "parent_no": os.environ.get("FILTER_COLUMN_PARENT_NO", "parent_serial_no"),
    "serial_no": os.environ.get("FILTER_COLUMN_SERIAL_NO", "serial_no"),
}

# Order the typing-combo filters cascade in: each one's dropdown is scoped to
# values that actually occur given the month/year plus every field before it
# here, so e.g. picking a job no. narrows what parent/serial no. can be.
CASCADE_FIELDS = ["line", "assignment_no", "parent_no", "serial_no"]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

def _generate_dropdown_arrow_icon(color, theme_name):
    """A small solid down-triangle PNG for QComboBox's drop-down arrow, one
    per theme since the color has to invert for a light background. Qt's QSS
    doesn't render the usual CSS border-triangle trick as a triangle (it just
    paints a filled block), so this draws one directly instead."""
    path = os.path.join(tempfile.gettempdir(), f"datarework_combo_arrow_{theme_name}.png")
    image = QImage(20, 20, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawPolygon(QPolygonF([QPointF(4, 7), QPointF(16, 7), QPointF(10, 14)]))
    painter.end()
    image.save(path)
    return path.replace("\\", "/")


def _sortable_key(text):
    try:
        return (0, float(text))
    except (TypeError, ValueError):
        return (1, text.lower())


def _get_settings():
    return QSettings("DataRework", "ProductionRework")


# Two color palettes for the same QSS template — everything that's a
# *surface* (backgrounds, borders, body text) swaps between them; the accent
# chips (Search/Clear/Save/Cancel, the focus ring, the checked-checkbox
# fill) stay fixed brand colors baked into the template since they're
# already tuned to read fine against both.
THEMES = {
    "dark": {
        "bg": "#0a0e14",
        "text": "#c7d3e0",
        "title": "#f2f6fb",
        "subtitle": "#5d7086",
        "badge_bg": "#101826",
        "badge_border": "#1f2c3f",
        "badge_text": "#9fb4cc",
        "badge_admin_text": "#8fe3ab",
        "badge_admin_border": "#1f4a33",
        "panel_bg": "#101722",
        "panel_border": "#1c2636",
        "panel_title": "#6f88a6",
        "input_bg": "#16273d",
        "input_text": "#eaf1fa",
        "input_border": "#24405e",
        "input_hover_border": "#3a6690",
        "popup_selection_bg": "#274a6e",
        "arrow_color": "#8fa5bf",
        "strip_bg": "#0d131d",
        "strip_border": "#1c2636",
        "checkbox_text": "#b6c4d6",
        "checkbox_bg": "#16273d",
        "checkbox_border": "#3a4d66",
        "table_bg": "#0d131d",
        "table_alt_bg": "#111a27",
        "table_text": "#dde6f0",
        "table_grid": "#1c2636",
        "table_border": "#1c2636",
        "table_sel_bg": "#274a6e",
        "table_sel_text": "#ffffff",
        "header_bg": "#141d2c",
        "header_text": "#8fa5bf",
        "header_border": "#24405e",
        "header_hover_bg": "#1b2738",
        "header_hover_text": "#c7d6e8",
        "status_error": "#e2879d",
        "status_ok": "#7fd6a3",
        "scrollbar_bg": "#0d131d",
        "scrollbar_handle": "#24405e",
        "save_disabled_bg": "#223228",
        "save_disabled_text": "#4c5c52",
    },
    "light": {
        "bg": "#eef1f6",
        "text": "#3b4757",
        "title": "#141a22",
        "subtitle": "#5b6b7d",
        "badge_bg": "#e4e9ef",
        "badge_border": "#d0d8e0",
        "badge_text": "#51606f",
        "badge_admin_text": "#188a52",
        "badge_admin_border": "#bfe8d0",
        "panel_bg": "#ffffff",
        "panel_border": "#dde3ea",
        "panel_title": "#4a7096",
        "input_bg": "#f7f9fb",
        "input_text": "#1c2733",
        "input_border": "#c7d2dd",
        "input_hover_border": "#8fa9c2",
        "popup_selection_bg": "#cfe3f7",
        "arrow_color": "#5b6b7d",
        "strip_bg": "#f7f9fb",
        "strip_border": "#dde3ea",
        "checkbox_text": "#3b4757",
        "checkbox_bg": "#ffffff",
        "checkbox_border": "#c7d2dd",
        "table_bg": "#ffffff",
        "table_alt_bg": "#f4f6f9",
        "table_text": "#1c2733",
        "table_grid": "#e3e8ee",
        "table_border": "#dde3ea",
        "table_sel_bg": "#cfe3f7",
        "table_sel_text": "#0d1b2a",
        "header_bg": "#eef1f5",
        "header_text": "#4a5b6d",
        "header_border": "#c7d2dd",
        "header_hover_bg": "#e2e8ef",
        "header_hover_text": "#1c2733",
        "status_error": "#c23a5c",
        "status_ok": "#178a4c",
        "scrollbar_bg": "#eef1f5",
        "scrollbar_handle": "#c7d2dd",
        "save_disabled_bg": "#e4e9ec",
        "save_disabled_text": "#a7b0b8",
    },
}

STYLE_TEMPLATE = """
QMainWindow, #central {
    background-color: __bg__;
}
QLabel {
    color: __text__;
    font-size: 13px;
}
#pageTitle {
    color: __title__;
    font-size: 21px;
    font-weight: 600;
}
#pageSubtitle, #stripLabel {
    color: __subtitle__;
    font-size: 12px;
}
#stripLabel {
    font-size: 11px;
    font-weight: 700;
}
#userBadge {
    color: __badge_text__;
    font-size: 12px;
    background-color: __badge_bg__;
    border: 1px solid __badge_border__;
    border-radius: 11px;
    padding: 5px 14px;
}
#userBadge[admin="true"] {
    color: __badge_admin_text__;
    border: 1px solid __badge_admin_border__;
}
#themeToggle {
    background-color: __badge_bg__;
    border: 1px solid __badge_border__;
    border-radius: 11px;
}
#themeToggle QPushButton {
    background-color: transparent;
    border: none;
    border-radius: 9px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    color: __subtitle__;
}
#themeToggle QPushButton:checked {
    background-color: #5b9bd5;
    color: #06131f;
}
QGroupBox {
    background-color: __panel_bg__;
    border: 1px solid __panel_border__;
    border-radius: 10px;
    margin-top: 6px;
    padding: 16px 14px 14px 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: __panel_title__;
    font-size: 11px;
    font-weight: 700;
}
QComboBox {
    background-color: __input_bg__;
    color: __input_text__;
    border: 1px solid __input_border__;
    border-radius: 6px;
    padding: 7px 10px;
    min-width: 108px;
    font-size: 13px;
}
QComboBox:hover {
    border: 1px solid __input_hover_border__;
}
QComboBox:focus {
    border: 1px solid #5b9bd5;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: url(__arrow_icon_path__);
    width: 10px;
    height: 10px;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: __input_bg__;
    color: __input_text__;
    selection-background-color: __popup_selection_bg__;
    border: 1px solid __input_border__;
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
#saveBtn:disabled { background-color: __save_disabled_bg__; color: __save_disabled_text__; }
#cancelBtn { background-color: #e2a0b3; color: #2a0d15; }
#cancelBtn:hover { background-color: #eab2c2; }
#columnsStrip {
    background-color: __strip_bg__;
    border: 1px solid __strip_border__;
    border-radius: 8px;
}
#columnsStrip QScrollArea, #columnsStrip QScrollArea > QWidget > QWidget, #columnsStrip QWidget#columnsStripInner {
    background-color: transparent;
    border: none;
}
QCheckBox {
    color: __checkbox_text__;
    font-size: 12px;
    spacing: 6px;
    padding: 2px 4px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid __checkbox_border__;
    background-color: __checkbox_bg__;
}
QCheckBox::indicator:checked {
    background-color: #5b9bd5;
    border: 1px solid #5b9bd5;
}
QTableWidget {
    background-color: __table_bg__;
    alternate-background-color: __table_alt_bg__;
    color: __table_text__;
    gridline-color: __table_grid__;
    border: 1px solid __table_border__;
    border-radius: 8px;
    selection-background-color: __table_sel_bg__;
    selection-color: __table_sel_text__;
    font-size: 12px;
}
QTableWidget::item {
    padding: 4px 6px;
}
QHeaderView::section {
    background-color: __header_bg__;
    color: __header_text__;
    border: none;
    border-bottom: 2px solid __header_border__;
    padding: 7px 6px;
    font-size: 11px;
    font-weight: 700;
}
QHeaderView::section:hover {
    background-color: __header_hover_bg__;
    color: __header_hover_text__;
}
#statusLabel[state="error"] { color: __status_error__; }
#statusLabel[state="ok"] { color: __status_ok__; }
QScrollBar:vertical, QScrollBar:horizontal {
    background: __scrollbar_bg__;
    width: 10px;
    height: 10px;
}
QScrollBar::handle {
    background: __scrollbar_handle__;
    border-radius: 5px;
}
"""


def _render_stylesheet(theme_name):
    theme = THEMES[theme_name]
    arrow_icon_path = _generate_dropdown_arrow_icon(theme["arrow_color"], theme_name)
    css = STYLE_TEMPLATE
    for token, value in theme.items():
        css = css.replace(f"__{token}__", value)
    return css.replace("__arrow_icon_path__", arrow_icon_path)


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
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
        self._theme = _get_settings().value("theme", "dark", type=str)
        if self._theme not in THEMES:
            self._theme = "dark"

        self.setWindowTitle("Production Rework")
        self.resize(1300, 700)
        self.setStyleSheet(_render_stylesheet(self._theme))

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

        row.addWidget(self._build_theme_toggle())

        badge = QLabel(f"{self.username}  ·  {self.permission}")
        badge.setObjectName("userBadge")
        badge.setProperty("admin", "true" if self.is_admin else "false")
        row.addWidget(badge, alignment=Qt.AlignVCenter)
        return row

    def _build_theme_toggle(self):
        frame = QFrame()
        frame.setObjectName("themeToggle")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.dark_theme_btn = QPushButton("Dark")
        self.light_theme_btn = QPushButton("Light")
        self._theme_buttons = {"dark": self.dark_theme_btn, "light": self.light_theme_btn}

        self._theme_button_group = QButtonGroup(frame)
        self._theme_button_group.setExclusive(True)
        for name, btn in self._theme_buttons.items():
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._theme_button_group.addButton(btn)
            btn.clicked.connect(lambda _checked=False, n=name: self._set_theme(n))
            layout.addWidget(btn)

        self._theme_buttons[self._theme].setChecked(True)
        return frame

    def _set_theme(self, name):
        if name not in THEMES:
            return
        self._theme = name
        self.setStyleSheet(_render_stylesheet(name))
        self._theme_buttons[name].setChecked(True)
        _get_settings().setValue("theme", name)

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
        label.setObjectName("stripLabel")
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
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
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

        if self._sort_column is not None and self._sort_column < self.table.columnCount():
            self._apply_sort()
        self._update_header_labels()

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

    def _on_header_clicked(self, logical_index):
        if self._show_delete_col and logical_index == 0:
            return  # Del column isn't a data column — nothing sensible to sort by

        if self._sort_column == logical_index:
            self._sort_order = (
                Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder else Qt.AscendingOrder
            )
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.AscendingOrder

        self._apply_sort()
        self._update_header_labels()

    def _apply_sort(self):
        offset = 1 if self._show_delete_col else 0
        sort_data_col = self._sort_column - offset
        row_count = self.table.rowCount()
        if row_count == 0:
            return

        bundles = []
        for r in range(row_count):
            cells = [self.table.item(r, c + offset).text() for c in range(len(self._columns))]
            deleted = False
            if self._show_delete_col:
                del_item = self.table.item(r, 0)
                deleted = bool(del_item and del_item.checkState() == Qt.Checked)
            bundles.append({
                "pk": self._row_pks[r],
                "original": self._row_originals[r],
                "cells": cells,
                "deleted": deleted,
            })

        bundles.sort(
            key=lambda b: _sortable_key(b["cells"][sort_data_col]),
            reverse=(self._sort_order == Qt.DescendingOrder),
        )

        self._row_pks = [b["pk"] for b in bundles]
        self._row_originals = [b["original"] for b in bundles]

        for r, b in enumerate(bundles):
            if self._show_delete_col:
                self.table.item(r, 0).setCheckState(Qt.Checked if b["deleted"] else Qt.Unchecked)
            for c, text in enumerate(b["cells"]):
                self.table.item(r, c + offset).setText(text)

    def _update_header_labels(self):
        offset = 1 if self._show_delete_col else 0
        headers = (["Del"] if self._show_delete_col else []) + self._columns
        for i, label in enumerate(headers):
            if i == self._sort_column:
                label += " ▲" if self._sort_order == Qt.AscendingOrder else " ▼"
            header_item = self.table.horizontalHeaderItem(i)
            if header_item:
                header_item.setText(label)

    def _reset_table(self):
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self._columns = []
        self._pk_columns = []
        self._row_pks = []
        self._row_originals = []
        self._show_delete_col = False
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
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
