import calendar
import datetime
import os

import psycopg2
from psycopg2 import sql
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QBrush, QColor
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
    QTabWidget,
    QVBoxLayout,
)

import db
from theme import THEMES, _render_stylesheet
from i18n import tr, column_label, language
from i18n_widgets import (QLabel, QPushButton, QCheckBox, QComboBox, QGroupBox,
                          QLineEdit, QWidget, QMainWindow, QDialog, QMessageBox, LanguageToggle)
from rename_dialog import ChildRelabelDialog, RenameContainerDialog
from delete_dialog import DeleteContainerDialog
from container_panel import ContainerPanel, LEVELS as CONTAINER_ORDER
from level_marks import level_mark
from debug_log import LOG, LogWindow

# --- Schema mapping --------------------------------------------------------
STAGING_TABLE = os.environ.get("STAGING_TABLE", "filling_product_logs")
DATE_COLUMN = os.environ.get("DATE_COLUMN", "created_at")
FILTER_COLUMNS = {
    "assignment_no": os.environ.get("FILTER_COLUMN_ASSIGNMENT_NO", "assignment_no"),
    "product_name": os.environ.get("FILTER_COLUMN_PRODUCT_NAME", "product_name"),

}

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

def _sortable_key(text):
    try:
        return (0, float(text))
    except (TypeError, ValueError):
        return (1, text.lower())


def _get_settings():
    return QSettings("DataRework", "ProductionRework")


class MainWindow(QMainWindow):
    def __init__(self, username, permission, tag_name):
        super().__init__()
        self.username = username
        self.permission = permission
        self.is_admin = permission == "admin"
        self.tag_name = tag_name

        self._columns = []
        self._pk_columns = []
        self._row_pks = []
        self._row_originals = []
        self._show_delete_col = False
        self._column_checks = {}
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
        self._log_window = None
        # The container whose records the grid is showing, if the user opened it
        # from a card. It narrows the grid only -- never the filter bar, and never
        # the container manager, so going back to the cards shows the whole level.
        self._record_scope = None
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
        self.views = QTabWidget()
        records_page = QWidget()
        records_layout = QVBoxLayout(records_page)
        records_layout.setContentsMargins(0, 10, 0, 0)
        records_layout.addWidget(self._build_scope_bar())
        records_layout.addWidget(self._build_columns_strip())
        records_layout.addWidget(self._build_table(), 1)
        self.views.addTab(records_page, tr('Records'))
        self.container_panel = ContainerPanel(self.is_admin)
        self.views.addTab(self.container_panel, tr('Container manager'))
        self.container_panel.refresh_requested.connect(self._refresh_containers)
        self.container_panel.rename_requested.connect(self._rename_from_manager)
        self.container_panel.delete_requested.connect(self._delete_from_manager)
        self.container_panel.records_requested.connect(self._open_container_records)
        self.container_panel.clear_filters_requested.connect(self._clear_container_filters)
        self.views.currentChanged.connect(self._view_changed)
        language.changed.connect(self._translate_tabs)
        root.addWidget(self.views, stretch=1)
        root.addLayout(self._build_footer())

        self._refresh_dependent_combos()
        language.changed.connect(self._retranslate_table)
        language.changed.connect(self._sync_filter_summary)

    # -- construction ------------------------------------------------------

    def _translate_tabs(self):
        self.views.setTabText(0, tr('Records'))
        self.views.setTabText(1, tr('Container manager'))

    def _view_changed(self, index):
        self._update_delete_button()
        self._apply_filter_collapse(self._filters_collapsed(index))
        if index == 1:
            self._refresh_containers()

    def _refresh_containers(self):
        try:
            columns = db.get_columns(STAGING_TABLE)
            conditions = self._current_conditions(columns) + self._category_tag_condition(columns)
            self.container_panel.set_groups(db.container_groups(
                STAGING_TABLE, columns, conditions, product_column=FILTER_COLUMNS['product_name']
            ))
            self.container_panel.set_filter_note(self._narrowing_filter_text())
        except Exception as exc:
            LOG.add(f"Could not load containers: {exc}", exc)
            self.container_panel.show_error()

    def _clear_container_filters(self):
        """Drop everything the container view is filtered by except the date.

        The date is how much data the app loads at all, not a choice about which
        containers to look at, so "Show all" leaves it where the user set it.
        """
        for combo in (self.job_combo, self.product_name_combo):
            combo.setCurrentText("")
        self.category_combo.setCurrentIndex(0)
        self.tag_value_edit.clear()
        self._refresh_dependent_combos()
        self._sync_filter_summary()
        self._refresh_containers()

    def _rename_from_manager(self, level, serial):
        self._rename_container(level, serial)
        self._refresh_containers()

    def _delete_from_manager(self, level, serial):
        self._delete_container(level, serial)

    def _open_container_records(self, path):
        """Show one container's rows in the grid, without touching the filters.

        Writing the serial into the category/tag/value boxes used to be how this
        worked, and it left the whole app pinned to one unit: the same boxes
        narrow the container manager, so coming back to the cards showed a single
        card until the user cleared the bar by hand. The path now travels with
        the search instead, and says so in a bar the user can dismiss.
        """
        if any(self._collect_changes()):
            self._show_status(tr('Save or cancel your pending edits before opening container records.'), error=True)
            return
        self._set_record_scope(path)
        self.views.setCurrentIndex(0)
        self._on_search(container_path=path)

    # -- the grid's container scope -------------------------------------------

    def _build_scope_bar(self):
        self.scope_bar = QFrame()
        self.scope_bar.setObjectName("scopeBar")
        row = QHBoxLayout(self.scope_bar)
        row.setContentsMargins(10, 5, 8, 5)
        row.setSpacing(8)
        self.scope_lead = QLabel()
        self.scope_lead.setObjectName("scopeLead")
        row.addWidget(self.scope_lead)
        self.scope_trail = QHBoxLayout()
        self.scope_trail.setSpacing(4)
        row.addLayout(self.scope_trail)
        row.addStretch(1)
        self.scope_clear = QPushButton(tr('Show all records'))
        self.scope_clear.setObjectName("scopeClear")
        self.scope_clear.setCursor(Qt.PointingHandCursor)
        self.scope_clear.setToolTip(tr('Stop showing only this container'))
        self.scope_clear.clicked.connect(self._clear_record_scope)
        row.addWidget(self.scope_clear)
        self.scope_bar.setVisible(False)
        return self.scope_bar

    def _set_record_scope(self, path):
        self._record_scope = tuple(path) if path else None
        while self.scope_trail.count():
            # Hold the widget: the layout item forgets it the moment it is
            # reparented, and item.widget() then answers None.
            widget = self.scope_trail.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.scope_bar.setVisible(self._record_scope is not None)
        if self._record_scope is None:
            return
        self.scope_lead.setText(tr('Showing the records in'))
        for index, serial in enumerate(self._record_scope):
            if index:
                self.scope_trail.addWidget(QLabel("›"))
            self.scope_trail.addWidget(
                self._scope_chip(CONTAINER_ORDER[index], serial))

    def _scope_chip(self, level, serial):
        chip = QFrame()
        chip.setObjectName("scopeChip")
        chip.setProperty("level", level)
        row = QHBoxLayout(chip)
        row.setContentsMargins(7, 2, 9, 2)
        row.setSpacing(5)
        mark = QLabel()
        mark.setPixmap(level_mark(level, 14))
        mark.setFixedSize(14, 14)
        row.addWidget(mark)
        name = QLabel(serial if serial not in (None, "") else tr('Unassigned'))
        name.setObjectName("scopeChipText")
        name.setTextFormat(Qt.PlainText)
        row.addWidget(name)
        chip.setToolTip(tr('{p0} {p1}', p0=tr(level.capitalize()),
                           p1=serial if serial not in (None, "") else tr('Unassigned')))
        return chip

    def _clear_record_scope(self):
        """Back to what the filter bar alone says, without disturbing the bar."""
        self._set_record_scope(None)
        self._on_search()

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
        # No QGroupBox title: the heading row below is the title, and it is what
        # stays on screen when the inputs are collapsed away.
        group = QGroupBox()
        self.filter_card = group
        group.setObjectName("filterCard")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        heading = QHBoxLayout()
        heading.setSpacing(10)
        title = QLabel(tr('Filters'))
        title.setObjectName("filterHeading")
        self.filter_summary = QLabel()
        self.filter_summary.setObjectName("filterSummary")
        self.filter_toggle = QPushButton(tr('Hide filters'))
        self.filter_toggle.setObjectName("filterToggle")
        self.filter_toggle.setCursor(Qt.PointingHandCursor)
        self.filter_toggle.clicked.connect(self._toggle_filters)
        heading.addWidget(title)
        heading.addWidget(self.filter_summary, 1)
        heading.addWidget(self.filter_toggle)
        outer.addLayout(heading)

        self.filter_body = QWidget()
        body = QVBoxLayout(self.filter_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        outer.addWidget(self.filter_body)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        body.addLayout(row1)
        body.addLayout(row2)

        self.day_combo = QComboBox()
        self.day_combo.addItem(tr('Day'), None)
        for d in range(1,32):
            self.day_combo.addItem(str(d), d)
        self.day_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.day_combo.setFixedWidth(96)

        self.month_combo = QComboBox()
        self.month_combo.addItem(tr('Month'), None)
        for i, name in enumerate(MONTH_NAMES, start=1):
            self.month_combo.addItem(tr(name), i)
        self.month_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.month_combo.setFixedWidth(156)

        self.year_combo = QComboBox()
        self.year_combo.addItem(tr('Year'), None)
        current_year = datetime.date.today().year
        for y in range(current_year - 1, current_year + 5):
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

        self.tag_value_combo = self._make_typing_combo(tr('Value'))
        self.tag_value_combo.setFixedWidth(230)
        self.tag_value_combo.setMaxVisibleItems(12)
        self.tag_value_combo.setEnabled(False)
        self.tag_value_combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.tag_value_combo.completer().setFilterMode(Qt.MatchContains)
        # Keep the line edit as the input used by the existing search logic.
        self.tag_value_edit = self.tag_value_combo.lineEdit()
        self.tag_value_edit.returnPressed.connect(self._on_value_enter)
        self.tag_combo.currentIndexChanged.connect(lambda _: self._refresh_tag_values(reset=True))

        # Row 1: date range + product name, which gets the leftover width so
        # long product names aren't cramped. Row 2: the remaining, narrower
        # filters plus the action buttons.
        for w in (self.day_combo, self.month_combo, self.year_combo):
            row1.addWidget(w)
        row1.addWidget(self.product_name_combo, stretch=1)

        for w in (self.job_combo, self.category_combo, self.tag_combo, self.tag_value_combo):
            row2.addWidget(w)

        # Date changes affect every downstream combo; each typing combo only
        # affects the ones after it in CASCADE_FIELDS. Refresh on
        # editingFinished/activated rather than every keystroke, so typing
        # doesn't fire a query per character.
        self.day_combo.currentIndexChanged.connect(lambda _=None: self._refresh_dependent_combos())
        self.month_combo.currentIndexChanged.connect(lambda _=None: self._on_date_changed())
        self.year_combo.currentIndexChanged.connect(lambda _=None: self._on_date_changed())
        # Month/year already carry today's date by now, so trim the day list
        # before it is ever shown.
        self._sync_day_range()
        for field_key in CASCADE_FIELDS:
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
        # A search the user asked for is about the filter bar, so it leaves the
        # one-container view behind. The same goes for a scanner's Enter in the
        # Value box below, which is a filter search by another route.
        self.search_btn.clicked.connect(self._on_filter_search)

        self.clear_btn = QPushButton(tr('Clear'))
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.clicked.connect(self._on_clear)

        row2.addWidget(self.clear_btn)
        row2.addWidget(self.search_btn)
        self._apply_filter_collapse(self._filters_collapsed(0))
        return group

    # -- the filter card folds away, and both tabs get the height --------------

    def _filters_key(self, index=None):
        if index is None:
            # Called once from _build_filter_bar, before the tabs exist.
            index = self.views.currentIndex() if hasattr(self, "views") else 0
        return "filters_collapsed_containers" if index == 1 else "filters_collapsed_records"

    def _filters_collapsed(self, index=None):
        """Folded or not, remembered per tab.

        The container manager opens folded because its cards are what the height
        is for; the records tab opens with the filters in reach, as it always
        has. Either choice sticks once the user makes it.
        """
        default = self._filters_key(index) == "filters_collapsed_containers"
        return _get_settings().value(self._filters_key(index), default, type=bool)

    def _apply_filter_collapse(self, collapsed):
        # The flag, not isVisible(): during construction the window is not shown
        # yet, so every child reports itself invisible and the summary would
        # appear next to filters that are in plain sight.
        self._filters_folded = collapsed
        self.filter_body.setVisible(not collapsed)
        self.filter_card.setProperty("collapsed", "true" if collapsed else "false")
        self.filter_card.style().unpolish(self.filter_card)
        self.filter_card.style().polish(self.filter_card)
        self.filter_toggle.setText(tr('Show filters') if collapsed else tr('Hide filters'))
        self._sync_filter_summary()

    def _sync_filter_summary(self):
        """The summary quotes filter values, so it is rebuilt rather than
        retranslated: a month name and a column label both change with the
        language, and the values between them do not."""
        self.filter_summary.setText(self._filter_summary() if self._filters_folded else "")

    def _toggle_filters(self):
        collapsed = not self._filters_folded
        _get_settings().setValue(self._filters_key(), collapsed)
        self._apply_filter_collapse(collapsed)

    def _filter_parts(self, date=True):
        """Each filter that is set, as a phrase; `date` includes the date one."""
        parts = []
        if date:
            # Day, month name, year, in that order and only the ones that are set.
            chosen = [str(self.day_combo.currentData()) if self.day_combo.currentData() else None,
                      self.month_combo.currentText() if self.month_combo.currentData() else None,
                      str(self.year_combo.currentData()) if self.year_combo.currentData() else None]
            chosen = [part for part in chosen if part]
            if chosen:
                parts.append(" ".join(chosen))
        for combo in (self.job_combo, self.product_name_combo):
            if combo.currentText().strip():
                parts.append(combo.currentText().strip())
        category, tag = self.category_combo.currentData(), self.tag_combo.currentData()
        value = self.tag_value_edit.text().strip()
        if category and tag and value:
            # column_label already names the level it belongs to.
            parts.append(f"{column_label(f'{category}_{tag}')} = {value}")
        return parts

    def _filter_summary(self):
        """What is still filtering the view while the inputs are out of sight."""
        parts = self._filter_parts()
        return tr('Filtering by {p0}', p0=" · ".join(parts)) if parts else tr('No filters applied')

    def _narrowing_filter_text(self):
        """What the container manager says above its cards, or "" for nothing.

        The date is left out on purpose: every search has one, so naming it would
        put a permanent notice over the cards that means nothing is wrong.
        """
        parts = self._filter_parts(date=False)
        return tr('Filtering by {p0}', p0=" · ".join(parts)) if parts else ""

    def _on_date_changed(self):
        self._sync_day_range()
        self._refresh_dependent_combos()

    def _sync_day_range(self):
        """Keep the day list to the days the chosen month really has, so
        February never offers a 30th.

        With no month picked there is nothing to trim. With a month but no
        year, the month could belong to any year, so February keeps its 29th
        rather than assuming a common year.
        """
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        if month is None:
            days = 31
        elif year is None:
            days = 29 if month == 2 else calendar.monthrange(2001, month)[1]
        else:
            days = calendar.monthrange(year, month)[1]

        if self.day_combo.count() == days + 1:  # +1 for the "Day" placeholder
            return

        kept = self.day_combo.currentData()
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        self.day_combo.addItem(tr('Day'), None)
        for d in range(1, days + 1):
            self.day_combo.addItem(str(d), d)
        # A day the new month doesn't have drops back to no day filter.
        self.day_combo.setCurrentIndex(max(self.day_combo.findData(kept), 0))
        self.day_combo.blockSignals(False)

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

        # Prefer serial numbers so choosing a category immediately offers values.
        if self.tag_combo.count() > 1:
            self.tag_combo.setCurrentIndex(1)
        self.tag_combo.blockSignals(False)
        self._refresh_tag_values(reset=True)

    def _refresh_tag_values(self, reset=False):
        """Offer distinct identifiers for this category/tag under the active filters."""
        kept_text = "" if reset else self.tag_value_edit.text()
        category = self.category_combo.currentData()
        tag = self.tag_combo.currentData()
        self.tag_value_combo.blockSignals(True)
        try:
            self.tag_value_combo.clear()
            self.tag_value_combo.setEnabled(bool(category and tag))
            if category and tag:
                columns = db.get_columns(STAGING_TABLE)
                column = f"{category}_{tag}"
                if column in columns:
                    values = db.fetch_distinct_values(
                        STAGING_TABLE, column,
                        conditions=self._current_conditions(columns), limit=None,
                    )
                    self.tag_value_combo.addItems(
                        [str(value) for value in values if value is not None and str(value).strip()]
                    )
        except Exception as exc:
            self._show_status(tr('Unable to load values. You can still type a value.'),
                              error=True, exc=exc)
        finally:
            # Populating choices must not silently select the first identifier.
            self.tag_value_combo.setCurrentIndex(-1)
            self.tag_value_combo.setCurrentText(kept_text)
            self.tag_value_combo.blockSignals(False)

    def _on_value_enter(self):
        if self.tag_value_edit.text().strip():
            self._on_filter_search()

    def _on_filter_search(self):
        self._set_record_scope(None)
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
        scroll.setFixedHeight(52)
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
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.itemSelectionChanged.connect(self._update_delete_button)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.verticalHeader().setMinimumSectionSize(34)
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
        self.status_label.setWordWrap(True)
        row.addWidget(self.status_label)

        # The status line is one short sentence; this opens the full text and
        # traceback behind it, so a failure can be diagnosed without a console.
        self.log_btn = QPushButton(tr('Log'))
        self.log_btn.setObjectName("logBtn")
        self.log_btn.setCheckable(True)
        self.log_btn.setToolTip(tr('Show full error details for debugging'))
        self.log_btn.clicked.connect(self._toggle_log)
        row.addWidget(self.log_btn)

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

        # Same reasoning as Rename: removing a container is not a cell edit, so it
        # neither queues with the grid's pending deletes nor waits for Save.
        self.delete_container_btn = QPushButton(tr('Delete container…'))
        self.delete_container_btn.setObjectName("ghostBtn")
        self.delete_container_btn.clicked.connect(lambda: self._delete_container())
        self.delete_container_btn.setEnabled(self.is_admin)
        if not self.is_admin:
            self.delete_container_btn.setToolTip(tr('Only admins can delete containers'))
        row.addWidget(self.delete_container_btn)

        self.delete_btn = QPushButton(tr('Delete'))
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.setToolTip(tr('Select rows by dragging, then mark them for deletion. Save applies the changes.'))
        self.delete_btn.clicked.connect(self._delete_selected_rows)
        self.delete_btn.setEnabled(False)
        row.addWidget(self.delete_btn)

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

    def _update_delete_button(self):
        if not hasattr(self, "delete_btn"):
            return
        records_visible = self.views.currentIndex() == 0
        self.delete_btn.setVisible(records_visible)
        self.delete_btn.setEnabled(
            records_visible and self.is_admin and self._show_delete_col
            and bool(self.table.selectionModel().selectedRows())
        )

    def _delete_selected_rows(self):
        if not self.is_admin or not self._show_delete_col or self.views.currentIndex() != 0:
            return
        rows = [index.row() for index in self.table.selectionModel().selectedRows()]
        if not rows:
            return
        for row in rows:
            self.table.item(row, 0).setCheckState(Qt.Checked)
        # Reveal the existing red deletion highlight underneath the selection.
        self.table.clearSelection()
        self._show_status(tr('{p0} row(s) marked for deletion. Save to apply, or uncheck Del to undo.', p0=len(rows)))

    def _date_conditions(self, columns):
        conditions = []
        day = self.day_combo.currentData()
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        if (day or month or year) and DATE_COLUMN in columns:
            if day:
                conditions.append(
                    (sql.SQL("EXTRACT(DAY FROM {}) = %s").format(sql.Identifier(DATE_COLUMN)), [day])
                )
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
            self._refresh_tag_values()
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

        self._refresh_tag_values()

    def _on_search(self, *, container_path=None):
        # Folded away, the heading line is the only thing still saying what the
        # view is filtered by, so keep it current.
        self._sync_filter_summary()
        if self.views.currentIndex() == 1 and any(self._collect_changes()):
            # Browsing saved containers must not discard edits in the Records tab.
            self._refresh_containers()
            return
        try:
            columns = db.get_columns(STAGING_TABLE)
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True, exc=exc)
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
        if container_path is not None:
            for level, serial in zip(CONTAINER_ORDER, container_path):
                column = f"{level}_serial_no"
                if column not in columns:
                    continue
                identifier = sql.Identifier(column)
                if serial is None:
                    conditions.append((sql.SQL("({0} IS NULL OR {0}::text = '')").format(identifier), []))
                else:
                    conditions.append((sql.SQL("{}::text = %s").format(identifier), [serial]))

        try:
            pk_columns = db.get_primary_key_columns(STAGING_TABLE)
            col_names, rows = db.query_rows(STAGING_TABLE, columns, conditions)
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True, exc=exc)
            return

        self._populate_table(col_names, rows, pk_columns)
        if self.views.currentIndex() == 1:
            self._refresh_containers()
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
        """self.month_combo.blockSignals(True)
        self.year_combo.blockSignals(True)
        self.month_combo.setCurrentIndex(0)
        self.year_combo.setCurrentIndex(0)
        self.month_combo.blockSignals(False)
        self.year_combo.blockSignals(False)"""
        for combo in (self.job_combo, self.product_name_combo):
            combo.setCurrentText("")
        self.category_combo.setCurrentIndex(0)
        self.tag_value_edit.clear()
        self._set_record_scope(None)
        self._refresh_dependent_combos()
        # Folded, the heading is the only record of what the filters say, so it
        # has to follow them back to empty.
        self._sync_filter_summary()
        self.container_panel.navigate(())
        self.container_panel.set_groups([])
        if self.views.currentIndex() == 1:
            self._refresh_containers()
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
            # One transaction: the mirror refuses a shared container before
            # filling_product_logs is touched, and a later failure rolls both back.
            db.save_grid_changes(
                STAGING_TABLE, self._pk_columns, updates, deletes,
                tag_name=self.tag_name,
            )
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except (db.SharedEdgeError, db.SerialConflictError,
                db.SerialInventoryError) as exc:
            self._show_status(str(exc), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(tr('Save failed: {p0}', p0=exc), error=True, exc=exc)
            return

        self._show_status(tr('Changes saved.'))
        # Still the same view the user was in, one container's rows or all of them.
        self._on_search(container_path=self._record_scope)

    def _on_table_context_menu(self, pos):
        """Offer "Rename this <level>..." and "Delete this <level>..." on a container serial."""
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
        delete_action = menu.addAction(tr('Delete this {p0}…', p0=tr(level)))
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is rename_action:
            self._rename_container(level, serial)
        elif chosen is delete_action:
            self._delete_container(level, serial)

    def _rename_container(self, level=None, old_serial=""):
        """Rename a container, then offer to carry the change down to its children.

        `level` / `old_serial` only pre-select the dialog — from the footer
        button both are empty and the user picks; from the grid's context menu
        they come from the cell that was right-clicked.
        """
        if not self.is_admin:
            return
        # A rename reloads the grid, so anything still pending would be lost.
        pending_updates, pending_deletes = self._collect_changes()
        if pending_updates or pending_deletes:
            self._show_status(
                tr('Save or cancel your pending edits before renaming a container.'), error=True
            )
            return

        dialog = RenameContainerDialog(self, level=level or "carton", serial=old_serial,
                                       scan_ready=not bool(old_serial))
        if dialog.exec() != QDialog.Accepted:
            return

        level = dialog.level
        old_serial, new_serial = dialog.values()
        if not old_serial or not new_serial or new_serial == old_serial:
            return

        try:
            preview = db.container_rename_preview(level, old_serial)
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(str(exc), error=True, exc=exc)
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
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except (db.SerialConflictError, db.SerialInventoryError) as exc:
            self._show_status(str(exc), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(tr('Rename failed: {p0}', p0=exc), error=True, exc=exc)
            return

        message = (
            tr('Renamed {p0} "{p1}" to "{p2}" — {p3} row(s), {p4} link(s).', p0=tr(level), p1=old_serial, p2=new_serial, p3=result["rows"], p4=result["edges"])
        )
        self._show_status(message)
        if level != "unit":
            self._show_status(message + self._relabel_children(level, old_serial, new_serial))
        self._on_search(container_path=self._record_scope)

    def _relabel_children(self, level, old_serial, new_serial):
        """Stage 2 — list what the renamed container holds and rename the ticked rows.

        Runs after the container rename has already committed, so the children
        are looked up under the *new* name. Returns the suffix to append to the
        status line; declining is a normal outcome, not a failure.
        """
        try:
            children = db.container_children(level, new_serial)
        except Exception as exc:
            LOG.add(f"Could not list children of {new_serial}: {exc}", exc)
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
        except psycopg2.OperationalError as exc:
            LOG.add("Child rename failed: unable to reach the database", exc)
            return tr(' Children unchanged: unable to reach the database.')
        except Exception as exc:
            LOG.add(f"Child rename failed: {exc}", exc)
            return tr(' Children unchanged: {p0}', p0=exc)

        return (
            tr(' Also renamed {p0} child serial(s), {p1} row(s).', p0=child_result["renamed"], p1=child_result["rows"])
        )

    def _delete_container(self, level=None, serial=""):
        """Delete a container and everything inside it, after showing what is inside.

        Like a rename this is not a cell edit: it happens at once instead of waiting
        for Save, and the reload afterwards would drop unsaved grid edits, so those
        are refused first. `level` / `serial` only pre-select the dialog -- empty
        from the footer button, filled from a right-clicked cell or a card.
        """
        if not self.is_admin:
            return
        pending_updates, pending_deletes = self._collect_changes()
        if pending_updates or pending_deletes:
            self._show_status(
                tr('Save or cancel your pending edits before deleting a container.'), error=True
            )
            return

        dialog = DeleteContainerDialog(self, table=STAGING_TABLE, level=level or "carton",
                                       serial=serial)
        if dialog.exec() != QDialog.Accepted:
            return

        level, serial, preview = dialog.level, dialog.serial(), dialog.preview()
        if not serial or preview is None:
            return

        question = tr(
            'Delete {p0} "{p1}" and everything inside it.\n\nThis permanently deletes {p2} row(s) in public.{p3} and {p4} link(s) in public.{p5}, and releases {p6} unit serial(s).',
            p0=tr(level), p1=serial, p2=preview["rows"], p3=STAGING_TABLE,
            p4=preview["edges"], p5=db.STAGING_EDGE_TABLE, p6=preview["units"],
        )
        if preview["emptied"]:
            names = tr(', ').join(
                [tr(item["level"]) + " " + item["serial_no"] for item in preview["emptied"]])
            question = question + tr(' It also removes {p0}, which would be left empty.', p0=names)
        question = question + tr(' This cannot be undone. Continue?')

        reply = QMessageBox.question(
            self, tr('Confirm delete'), question,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # `expected` makes the database refuse if the contents changed since the
            # user reviewed them, instead of deleting something they never saw.
            result = db.delete_container(level, serial, table=STAGING_TABLE,
                                         tag_name=self.tag_name, expected=preview)
        except psycopg2.OperationalError as exc:
            self._show_status(tr('Unable to reach the database'), error=True, exc=exc)
            return
        except db.ContainerDeleteError as exc:
            self._show_status(str(exc), error=True, exc=exc)
            return
        except Exception as exc:
            self._show_status(tr('Delete failed: {p0}', p0=exc), error=True, exc=exc)
            return

        note = (f' {result["orphans"]} saved row reference(s) named a link that no longer '
                "existed and were skipped." if result.get("orphans") else "")
        LOG.add(
            f'Deleted {level} "{serial}": {result["rows"]} row(s), {result["edges"]} link(s), '
            f'{result["units"]} unit serial(s) released ({self.tag_name}).{note}',
            level="INFO",
        )
        self._on_search(container_path=self._record_scope)
        # The reload reports "N row(s) loaded."; keep the delete's own outcome on
        # screen unless the reload itself failed.
        if self.status_label.property("state") != "error":
            self._show_status(tr(
                'Deleted {p0} "{p1}" — {p2} row(s), {p3} link(s), {p4} unit serial(s) released.',
                p0=tr(level), p1=serial, p2=result["rows"], p3=result["edges"], p4=result["units"],
            ))

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

    def _show_status(self, message, error=False, exc=None):
        """Show one short line; `exc` files the full traceback under the Log button."""
        self.status_label.setText(message)
        self.status_label.setProperty("state", "error" if error else "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if error:
            LOG.add(message, exc)

    def _toggle_log(self, checked):
        """Open/close the log window. Created lazily; the button tracks its state."""
        if not checked:
            if self._log_window is not None:
                self._log_window.close()
            return
        if self._log_window is None:
            self._log_window = LogWindow(self)
            # Closing via the window's own X or Close button must untick the toggle.
            self._log_window.finished.connect(
                lambda _result: self.log_btn.setChecked(False)
            )
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()
