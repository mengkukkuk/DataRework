import datetime
import os
import re
import tempfile

import psycopg2
from psycopg2 import sql
from PySide6.QtCore import Qt, QPointF, QSettings
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import db
from i18n import tr, column_label, language
from i18n_widgets import (QLabel, QPushButton, QCheckBox, QComboBox, QGroupBox,
                          QLineEdit, QWidget, QMainWindow, QDialog, QMessageBox, LanguageToggle)
from rename_dialog import ChildRelabelDialog, RenameContainerDialog

# --- Schema mapping --------------------------------------------------------
STAGING_TABLE = os.environ.get("STAGING_TABLE", "filling_product_logs")
DATE_COLUMN = os.environ.get("DATE_COLUMN", "created_at")
FILTER_COLUMNS = {
    "assignment_no": os.environ.get("FILTER_COLUMN_ASSIGNMENT_NO", "assignment_no"),
    "product_name": os.environ.get("FILTER_COLUMN_PRODUCT_NAME", "product_name"),

}

#CASCADE_FIELDS = ["line", "assignment_no", "parent_no", "serial_no"]
CASCADE_FIELDS = [ "assignment_no", "product_name"]

# Each region of the product (unit/inner/display/carton) has its own set of
# id-tracking columns, named "<region>_<tag>" (e.g. "unit_serial_no"). Not
# every region has every tag (unit has no target_id, carton has no
# source_id), so the tag dropdown is populated from the table's actual
# columns rather than this full candidate list.
# A display/inner/carton serial names a container that many rows share, so it
# has no meaning as a per-row cell edit: typing over one row's display_serial_no
# either renames the container for every sibling too, or silently desyncs
# staging_product_logs. Those cells are read-only and carry a right-click
# "Rename this <level>..." action instead, which rewrites the whole container.
# unit_* stays inline-editable — it is genuinely 1:1 with the row.
CONTAINER_SERIAL_COLUMNS = {f"{lvl}_serial_no": lvl for lvl in db.CONTAINER_LEVELS}
READONLY_COLUMNS = set(CONTAINER_SERIAL_COLUMNS) | {
    f"{lvl}_roll_no" for lvl in db.CONTAINER_LEVELS
}

REGION_CATEGORIES = ["unit", "inner", "display", "carton"]
REGION_TAGS = ["serial_no", "roll_no", "source_id", "target_id"]
REGION_TAG_LABELS = {
    "serial_no": "Serial No",
    "roll_no": "Roll No",
    "source_id": "Source ID",
    "target_id": "Target ID",
}

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Background/foreground used to highlight a cell whose value has been edited
# but not yet saved, independent of the light/dark theme so it stays legible
# against either table background.
EDITED_CELL_BG = QColor("#7fe0b0")
EDITED_CELL_FG = QColor("#06301c")

# Background/foreground used to mark every cell in a row whose Del checkbox
# is ticked, so it's obvious which rows will be removed on Save.
DELETED_ROW_BG = QColor("#f28b8b")
DELETED_ROW_FG = QColor("#3d0606")

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


# THEMES (the two color palettes) and the QSS template both live in
# style.css, next to this file — see that file's header comment for why
# they're written as :root[data-theme="..."] custom-property blocks even
# though Qt's QSS engine can't use CSS variables natively: this module
# parses them itself and does the __token__ substitution below, so Qt only
# ever sees a flat stylesheet with literal values, exactly as before.
_THEME_BLOCK_RE = re.compile(r':root\[data-theme=["\'](\w+)["\']\]\s*\{([^}]*)\}', re.DOTALL)
_CSS_VAR_RE = re.compile(r'--([\w-]+)\s*:\s*([^;]+);')

def _load_style_source():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    themes = {}
    for match in _THEME_BLOCK_RE.finditer(content):
        theme_name, body = match.group(1), match.group(2)
        themes[theme_name] = {
            key.replace("-", "_"): value.strip()
            for key, value in _CSS_VAR_RE.findall(body)
        }

    template = _THEME_BLOCK_RE.sub("", content).strip()
    return themes, template


THEMES, STYLE_TEMPLATE = _load_style_source()


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

        self.setWindowTitle(tr('Production Rework'))
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
        language.changed.connect(self._retranslate_table)

    # -- construction ------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(tr('Production Rework'))
        title.setObjectName("pageTitle")
        subtitle = QLabel(tr('Table = {p0}', p0=STAGING_TABLE))
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        row.addLayout(title_box)
        row.addStretch(1)

        row.addWidget(LanguageToggle(self))
        row.addWidget(self._build_theme_toggle())

        badge = QLabel(tr('{p0}  ·  {p1}', p0=self.username, p1=tr(self.permission)))
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

        self.dark_theme_btn = QPushButton(tr('Dark'))
        self.light_theme_btn = QPushButton(tr('Light'))
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
        group = QGroupBox(tr('Filters'))
        outer = QVBoxLayout(group)
        outer.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        outer.addLayout(row1)
        outer.addLayout(row2)

        self.month_combo = QComboBox()
        self.month_combo.addItem(tr('Month'), None)
        for i, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(tr(name), i)
        self.month_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.month_combo.setFixedWidth(130)

        self.year_combo = QComboBox()
        self.year_combo.addItem(tr('Year'), None)
        current_year = datetime.date.today().year
        for y in range(current_year - 5, current_year + 2):
            self.year_combo.addItem(str(y), y)
        self.year_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.year_combo.setFixedWidth(100)

        today = datetime.date.today()
        self.month_combo.setCurrentIndex(self.month_combo.findData(today.month))
        self.year_combo.setCurrentIndex(self.year_combo.findData(today.year))

        self.product_name_combo = self._make_typing_combo(tr('Product name'))
        self.job_combo = self._make_typing_combo(tr('Ass. job no.'))
        self._cascade_combos = {
            "product_name": self.product_name_combo,
            "assignment_no": self.job_combo,
        }

        self.category_combo = QComboBox()
        self.category_combo.addItem(tr('Category'), None)
        for category in REGION_CATEGORIES:
            self.category_combo.addItem(tr(category.capitalize()), category)
        self.category_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.category_combo.setMinimumWidth(155)
        self.category_combo.currentIndexChanged.connect(lambda _=None: self._on_category_changed())

        self.tag_combo = QComboBox()
        self.tag_combo.addItem(tr('Tag'), None)
        self.tag_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tag_combo.setMinimumWidth(145)
        self.tag_combo.setEnabled(False)

        self.tag_value_edit = QLineEdit()
        self.tag_value_edit.setPlaceholderText(tr('Value'))
        self.tag_value_edit.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.tag_value_edit.setFixedWidth(150)
        self.tag_value_edit.returnPressed.connect(self._on_value_enter)

        # Row 1: date range + product name, which gets the leftover width so
        # long product names aren't cramped. Row 2: the remaining, narrower
        # filters plus the action buttons.
        for w in (self.month_combo, self.year_combo):
            row1.addWidget(w)
        row1.addWidget(self.product_name_combo, stretch=1)

        for w in (self.job_combo, self.category_combo, self.tag_combo, self.tag_value_edit):
            row2.addWidget(w)

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

        row2.addStretch(1)

        self.search_btn = QPushButton(tr('Search'))
        self.search_btn.setObjectName("searchBtn")
        self.search_btn.clicked.connect(self._on_search)

        self.clear_btn = QPushButton(tr('Clear'))
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self._on_clear)

        row2.addWidget(self.clear_btn)
        row2.addWidget(self.search_btn)
        return group

    def _on_category_changed(self):
        category = self.category_combo.currentData()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem(tr('Tag'), None)

        if category:
            try:
                columns = db.get_columns(STAGING_TABLE)
            except Exception as exc:
                print(f"Could not load tags for {category}: {exc}")
                columns = []
            for tag in REGION_TAGS:
                if f"{category}_{tag}" in columns:
                    self.tag_combo.addItem(tr(REGION_TAG_LABELS[tag]), tag)
            self.tag_combo.setEnabled(True)
        else:
            self.tag_combo.setEnabled(False)

        self.tag_combo.blockSignals(False)
        self.tag_value_edit.clear()

    def _on_value_enter(self):
        if self.tag_value_edit.text().strip():
            self._on_search()

    def _make_typing_combo(self, placeholder):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setLineEdit(QLineEdit(combo))
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.lineEdit().setPlaceholderText(placeholder)
        combo.setCurrentText("")
        if placeholder.key == "Product name":
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) # Flexible width for long names.
            combo.setMinimumWidth(250)
        else:
            combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed) # Fixed width for short names.
            combo.setFixedWidth(170)
        return combo

    def _build_columns_strip(self):
        frame = QFrame()
        frame.setObjectName("columnsStrip")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(10, 4, 10, 4)

        label = QLabel(tr('Columns'))
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
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        return self.table

    def _build_footer(self):
        row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        row.addWidget(self.status_label)
        row.addStretch(1)

        # Sits outside the grid because a rename is not a cell edit: it rewrites
        # one container across every row that names it, so it neither queues up
        # with the pending edits nor waits for Save.
        self.rename_btn = QPushButton(tr('Rename container…'))
        self.rename_btn.setObjectName("ghostBtn")
        self.rename_btn.clicked.connect(lambda: self._rename_container())
        self.rename_btn.setEnabled(self.is_admin)
        if not self.is_admin:
            self.rename_btn.setToolTip(tr('Only admins can rename containers'))
        row.addWidget(self.rename_btn)

        self.save_btn = QPushButton(tr('Save'))
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(self.is_admin)
        if not self.is_admin:
            self.save_btn.setToolTip(tr('Only admins can save changes'))

        self.cancel_btn = QPushButton(tr('Cancel'))
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

    def _category_tag_condition(self, columns):
        """WHERE condition for the category+tag+value filter, e.g. category
        "unit" and tag "serial_no" resolve to the unit_serial_no column.
        Returns [] if the filter isn't fully specified or doesn't resolve to
        a real column."""
        category = self.category_combo.currentData()
        tag = self.tag_combo.currentData()
        value = self.tag_value_edit.text().strip()
        if not (category and tag and value):
            return []

        column = f"{category}_{tag}"
        if column not in columns:
            return []

        # source_id/target_id are integer columns; cast to text so this
        # works uniformly across columns. ILIKE with no wildcards is an
        # exact, case-insensitive match (not a substring search).
        return [(sql.SQL("{}::text ILIKE %s").format(sql.Identifier(column)), [value])]

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
            self._show_status(tr('Unable to reach the database'), error=True)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True)
            return

        if not columns:
            self._show_status(tr('Table "public.{p0}" was not found.', p0=STAGING_TABLE), error=True)
            self._reset_table()
            return

        warnings = []
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        if (month or year) and DATE_COLUMN not in columns:
            warnings.append(tr('date filter skipped (no date column)'))

        for field_key in CASCADE_FIELDS:
            value = self._cascade_combos[field_key].currentText().strip()
            if value and (FILTER_COLUMNS.get(field_key) not in columns):
                warnings.append(tr('{p0} filter skipped (no such column)', p0=column_label(field_key)))

        category = self.category_combo.currentData()
        tag = self.tag_combo.currentData()
        tag_value = self.tag_value_edit.text().strip()
        if tag_value and not (category and tag):
            warnings.append(tr('tag value ignored (pick a category and tag first)'))
        elif category and tag and not tag_value:
            warnings.append(tr('category/tag filter skipped (no value entered)'))

        conditions = self._current_conditions(columns)
        conditions += self._category_tag_condition(columns)

        try:
            pk_columns = db.get_primary_key_columns(STAGING_TABLE)
            col_names, rows = db.query_rows(STAGING_TABLE, columns, conditions)
        except psycopg2.OperationalError:
            self._show_status(tr('Unable to reach the database'), error=True)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True)
            return

        self._populate_table(col_names, rows, pk_columns)
        message = tr('{p0} row(s) loaded.', p0=len(rows))
        if warnings:
            message += " " + tr("; ").join(warnings)
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
        headers = ([tr("Del")] if self._show_delete_col else []) + [column_label(c) for c in columns]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))

        self._row_pks = []
        self._row_originals = []

        # Loading fresh rows sets every item's text, which would otherwise
        # fire itemChanged (and thus the edited-cell highlight check) once
        # per cell for no reason — block it for the duration of the load.
        self.table.blockSignals(True)
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
                if editable and col not in READONLY_COLUMNS:
                    flags |= Qt.ItemIsEditable
                item.setFlags(flags)
                if col in CONTAINER_SERIAL_COLUMNS:
                    item.setToolTip(
                        tr('Shared {p0} — right-click to rename it across every row it holds.', p0=tr(CONTAINER_SERIAL_COLUMNS[col]))
                    )
                elif col in READONLY_COLUMNS:
                    item.setToolTip(tr('Belongs to a shared container — not editable per row.'))
                self.table.setItem(r, c + offset, item)
        self.table.blockSignals(False)

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
            cb = QCheckBox(column_label(col))
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
        headers = ([tr("Del")] if self._show_delete_col else []) + [column_label(c) for c in self._columns]
        for i, label in enumerate(headers):
            if i == self._sort_column:
                label += " ▲" if self._sort_order == Qt.AscendingOrder else " ▼"
            header_item = self.table.horizontalHeaderItem(i)
            if header_item:
                header_item.setText(label)

    def _retranslate_table(self):
        self._update_header_labels()
        offset = int(self._show_delete_col)
        self.table.blockSignals(True)
        try:
            for c, col in enumerate(self._columns):
                if col not in READONLY_COLUMNS:
                    continue
                tooltip = (
                    tr('Shared {p0} — right-click to rename it across every row it holds.',
                       p0=tr(CONTAINER_SERIAL_COLUMNS[col]))
                    if col in CONTAINER_SERIAL_COLUMNS else
                    tr('Belongs to a shared container — not editable per row.')
                )
                for r in range(self.table.rowCount()):
                    self.table.item(r, c + offset).setToolTip(tooltip)
        finally:
            self.table.blockSignals(False)
        self.table.resizeColumnsToContents()

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
        for combo in (self.job_combo, self.product_name_combo):
            combo.setCurrentText("")
        self.category_combo.setCurrentIndex(0)
        self.tag_value_edit.clear()
        self._refresh_dependent_combos()
        self.status_label.clear()
        self.status_label.setProperty("state", "")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_cancel(self):
        self._on_clear()
        self._reset_table()
        self._show_status(tr('Cleared.'))

    def _on_save(self):
        if not self.is_admin:
            self._show_status(tr('Only admins can save changes.'), error=True)
            return
        if not self._pk_columns:
            self._show_status(tr('This table has no primary key — nothing can be saved.'), error=True)
            return

        updates, deletes = self._collect_changes()
        if not updates and not deletes:
            self._show_status(tr('No changes to save.'))
            return

        parts = []
        if updates:
            parts.append(tr('update {p0} row(s)', p0=len(updates)))
        if deletes:
            parts.append(tr('delete {p0} row(s)', p0=len(deletes)))

        reply = QMessageBox.question(
            self,
            tr('Confirm changes'),
            tr('This will {p0} in public.{p1}. This cannot be undone. Continue?', p0=tr(' and ').join(parts), p1=STAGING_TABLE),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # BEFORE we save, check that the user has actually made any changes.
        # If they haven't, we don't want to save anything, since it would
        # overwrite the existing data.
        if not updates and not deletes:
            self._show_status(tr('No changes to save.'))
            return
        try:
            # Mirrors the edit into staging_product_logs first: it refuses the
            # save on a shared container before filling_product_logs is touched.
            db.update_staging_serial_data(updates, deletes, self._pk_columns)
            db.save_changes(STAGING_TABLE, self._pk_columns, updates, deletes)
        except psycopg2.OperationalError:
            self._show_status(tr('Unable to reach the database'), error=True)
            return
        except (db.SharedEdgeError, db.SerialConflictError) as exc:
            self._show_status(str(exc), error=True)
            return
        except Exception as exc:
            self._show_status(tr('Save failed: {p0}', p0=exc), error=True)
            return

        self._show_status(tr('Changes saved.'))
        self._on_search()

    def _on_table_context_menu(self, pos):
        """Offer "Rename this <level>..." when the click lands on a container serial."""
        if not self.is_admin:
            return
        item = self.table.itemAt(pos)
        if item is None:
            return

        offset = 1 if self._show_delete_col else 0
        data_col = item.column() - offset
        if not (0 <= data_col < len(self._columns)):
            return

        level = CONTAINER_SERIAL_COLUMNS.get(self._columns[data_col])
        serial = item.text().strip()
        if not level or not serial:
            return

        menu = QMenu(self)
        rename_action = menu.addAction(tr('Rename this {p0}…', p0=tr(level)))
        if menu.exec(self.table.viewport().mapToGlobal(pos)) is rename_action:
            self._rename_container(level, serial)

    def _rename_container(self, level=None, old_serial=""):
        """Rename a container, then offer to carry the change down to its children.

        `level` / `old_serial` only pre-select the dialog — from the footer
        button both are empty and the user picks; from the grid's context menu
        they come from the cell that was right-clicked.
        """
        # A rename reloads the grid, so anything still pending would be lost.
        pending_updates, pending_deletes = self._collect_changes()
        if pending_updates or pending_deletes:
            self._show_status(
                tr('Save or cancel your pending edits before renaming a container.'), error=True
            )
            return

        dialog = RenameContainerDialog(self, level=level or "carton", serial=old_serial)
        if dialog.exec() != QDialog.Accepted:
            return

        level = dialog.level
        old_serial, new_serial = dialog.values()
        if not old_serial or not new_serial or new_serial == old_serial:
            return

        try:
            preview = db.container_rename_preview(level, old_serial)
        except psycopg2.OperationalError:
            self._show_status(tr('Unable to reach the database'), error=True)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True)
            return

        reply = QMessageBox.question(
            self,
            tr('Confirm rename'),
            tr('Rename {p0} "{p1}" to "{p2}".\n\nThis updates {p3} row(s) in public.{p4} and {p5} link(s) in public.{p6}. This cannot be undone. Continue?', p0=tr(level), p1=old_serial, p2=new_serial, p3=preview["rows"], p4=STAGING_TABLE, p5=preview["edges"], p6=db.STAGING_EDGE_TABLE),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            result = db.rename_container(level, old_serial, new_serial)
        except psycopg2.OperationalError:
            self._show_status(tr('Unable to reach the database'), error=True)
            return
        except db.SerialConflictError as exc:
            self._show_status(str(exc), error=True)
            return
        except Exception as exc:
            self._show_status(tr('Rename failed: {p0}', p0=exc), error=True)
            return

        message = (
            tr('Renamed {p0} "{p1}" to "{p2}" — {p3} row(s), {p4} link(s).', p0=tr(level), p1=old_serial, p2=new_serial, p3=result["rows"], p4=result["edges"])
        )
        self._show_status(message)
        self._show_status(message + self._relabel_children(level, old_serial, new_serial))
        self._on_search()

    def _relabel_children(self, level, old_serial, new_serial):
        """Stage 2 — list what the renamed container holds and rename the ticked rows.

        Runs after the container rename has already committed, so the children
        are looked up under the *new* name. Returns the suffix to append to the
        status line; declining is a normal outcome, not a failure.
        """
        try:
            children = db.container_children(level, new_serial)
        except Exception as exc:
            return tr(' Could not list its children: {p0}', p0=exc)
        if not children:
            return ""

        dialog = ChildRelabelDialog(self, level, old_serial, new_serial, children)
        if dialog.exec() != QDialog.Accepted:
            return ""

        renames = dialog.renames()
        if not renames:
            return ""

        try:
            child_result = db.rename_children(renames)
        except psycopg2.OperationalError:
            return tr(' Children unchanged: unable to reach the database.')
        except Exception as exc:
            return tr(' Children unchanged: {p0}', p0=exc)

        return (
            tr(' Also renamed {p0} child serial(s), {p1} row(s).', p0=child_result["renamed"], p1=child_result["rows"])
        )

    def _on_item_changed(self, item):
        """Glow a cell green while its value differs from what was loaded, or
        glow the whole row red while its Del checkbox is ticked, so it's
        obvious what's still pending before Save."""
        col = item.column()
        row = item.row()
        offset = 1 if self._show_delete_col else 0

        if self._show_delete_col and col == 0:
            self._apply_row_delete_highlight(row, item.checkState() == Qt.Checked)
            return  # Del checkbox, not an editable data cell

        data_col = col - offset
        if row >= len(self._row_originals) or not (0 <= data_col < len(self._columns)):
            return

        if self._is_row_marked_deleted(row):
            # Row is already slated for deletion — keep it red rather than
            # flipping it green, since any edit here is moot on Save.
            item.setBackground(DELETED_ROW_BG)
            item.setForeground(DELETED_ROW_FG)
            return

        column_name = self._columns[data_col]
        original_value = self._row_originals[row].get(column_name)
        original_text = "" if original_value is None else str(original_value)

        if item.text() != original_text:
            item.setBackground(EDITED_CELL_BG)
            item.setForeground(EDITED_CELL_FG)
        else:
            item.setBackground(QBrush())
            item.setForeground(QBrush())

    def _is_row_marked_deleted(self, row):
        if not self._show_delete_col:
            return False
        del_item = self.table.item(row, 0)
        return bool(del_item and del_item.checkState() == Qt.Checked)

    def _apply_row_delete_highlight(self, row, deleted):
        """Paint (or unpaint) every data cell in `row` red for the Del
        checkbox, restoring each cell's edited-green state on uncheck."""
        offset = 1 if self._show_delete_col else 0
        original = self._row_originals[row] if row < len(self._row_originals) else {}
        for c, column_name in enumerate(self._columns):
            cell = self.table.item(row, c + offset)
            if not cell:
                continue
            if deleted:
                cell.setBackground(DELETED_ROW_BG)
                cell.setForeground(DELETED_ROW_FG)
                continue

            original_value = original.get(column_name)
            original_text = "" if original_value is None else str(original_value)
            if cell.text() != original_text:
                cell.setBackground(EDITED_CELL_BG)
                cell.setForeground(EDITED_CELL_FG)
            else:
                cell.setBackground(QBrush())
                cell.setForeground(QBrush())

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
