"""Browse packaging as nested crates, using persisted records and full paths."""
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal, QEvent, QSize, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout

from i18n import tr, language
from i18n_widgets import QLabel, QLineEdit, QPushButton, QWidget
from level_marks import level_icon, level_mark
from product_avatars import AvatarCatalog, avatar_pixmap
from image_preview import AvatarLabel, ImagePreview

LEVELS = ("carton", "inner", "display", "unit")
PAGE_SIZE = 20
CARD_HEIGHT = 132
CARD_WIDTH = 250
GRID_GAP = 8


@dataclass
class ContainerNode:
    path: tuple = ()
    rows: int = 0
    children: dict = field(default_factory=dict)
    products: set = field(default_factory=set)


def build_hierarchy(groups):
    root = ContainerNode()
    for group in groups:
        serials, count = group[:4], group[4]
        products = {str(name) for name in (group[5] or []) if name} if len(group) > 5 else set()
        node = root
        node.rows += count
        node.products.update(products)
        for serial in serials:
            serial = None if serial is None or str(serial) == "" else str(serial)
            node = node.children.setdefault(serial, ContainerNode(node.path + (serial,)))
            node.rows += count
            node.products.update(products)
    return root


class ContainerPanel(QWidget):
    refresh_requested = Signal()
    rename_requested = Signal(str, str)
    delete_requested = Signal(str, str)
    records_requested = Signal(object)

    def __init__(self, is_admin, parent=None):
        super().__init__(parent)
        self.setObjectName("containerManager")
        self.is_admin = is_admin
        self.avatars = AvatarCatalog()
        self.root = ContainerNode()
        self.path = ()
        # Where the user has been, oldest first, and where in it they are now.
        # Drilling in from a card and clicking a breadcrumb both land here, so
        # Back retraces the route rather than only climbing one level.
        self.history = [()]
        self.history_at = 0
        self.page = 0
        self.cards = []
        self._grid_columns = 5
        self.page_size = PAGE_SIZE
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)
        top = QHBoxLayout()
        # Title and hint share one row with the search box: two lines of heading
        # where there were three, and the difference goes to the cards.
        heading_box = QVBoxLayout()
        heading_box.setSpacing(0)
        title = QLabel(tr("Container manager"))
        title.setObjectName("dialogTitle")
        heading_box.addWidget(title)
        hint = QLabel(tr("Browse saved records: carton → inner → display → unit. Counts follow the active filters."))
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        heading_box.addWidget(hint)
        # The hint takes the width left over by the search box rather than
        # wrapping into a four-line block.
        top.addLayout(heading_box, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Find serial in this level"))
        self.search.setObjectName("containerSearch")
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self._filter_changed)
        top.addWidget(self.search)
        refresh = QPushButton(tr("Refresh"))
        refresh.setObjectName("ghostBtn")
        refresh.clicked.connect(self.refresh_requested.emit)
        top.addWidget(refresh)
        layout.addLayout(top)
        # One route row: Back/Forward, the trail, and the count of what is in view.
        route = QHBoxLayout()
        route.setSpacing(6)
        self.back_btn = QPushButton("←")
        self.back_btn.setObjectName("navBtn")
        self.back_btn.clicked.connect(self.go_back)
        self.forward_btn = QPushButton("→")
        self.forward_btn.setObjectName("navBtn")
        self.forward_btn.clicked.connect(self.go_forward)
        for button in (self.back_btn, self.forward_btn):
            button.setFixedWidth(34)
            button.setCursor(Qt.PointingHandCursor)
            route.addWidget(button)
        self.breadcrumbs = QHBoxLayout()
        self.breadcrumbs.setSpacing(4)
        route.addLayout(self.breadcrumbs, 1)
        self.summary = QLabel()
        self.summary.setObjectName("containerSummary")
        route.addWidget(self.summary, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addLayout(route)
        # Scoped to this panel: Alt+Left on the records tab is not a request to
        # move a container view nobody is looking at.
        for keys, slot in ((QKeySequence.Back, self.go_back),
                           (QKeySequence.Forward, self.go_forward)):
            shortcut = QShortcut(keys, self, activated=slot)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.inner = QWidget()
        self.inner.setObjectName("containerGrid")
        # Pagination owns overflow; the grid must not grow the window to fit items.
        self.inner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.inner.setMinimumHeight(CARD_HEIGHT)
        self.inner.installEventFilter(self)
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GRID_GAP)
        self.grid.setAlignment(Qt.AlignTop)
        layout.addWidget(self.inner, 1)
        bottom = QHBoxLayout()
        self.previous = QPushButton(tr("← Previous"))
        self.previous.setObjectName("ghostBtn")
        self.previous.clicked.connect(lambda: self._change_page(-1))
        self.next = QPushButton(tr("Next →"))
        self.next.setObjectName("ghostBtn")
        self.next.clicked.connect(lambda: self._change_page(1))
        self.page_label = QLabel()
        bottom.addStretch()
        bottom.addWidget(self.page_label)
        bottom.addStretch()
        bottom.addWidget(self.previous)
        bottom.addWidget(self.next)
        layout.addLayout(bottom)
        language.changed.connect(self.render)
        self.render()

    def set_groups(self, groups):
        self.root = build_hierarchy(groups)
        node = self.root
        valid = ()
        for serial in self.path:
            if serial not in node.children:
                break
            node = node.children[serial]
            valid += (serial,)
        if valid != self.path:
            self.history, self.history_at = [valid], 0
        self.path = valid
        self.render()

    def show_error(self):
        self.set_groups([])
        self._set_summary(tr("Unable to load containers. Try Refresh."), error=True)

    def _set_summary(self, text, error=False):
        """The count of what is in view, or why there is nothing in view."""
        self.summary.setText(text)
        self.summary.setProperty("state", "error" if error else "")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)

    def navigate(self, path, record=True):
        """Show `path`. `record` is what separates a move from a retrace: Back
        and Forward replay the trail without rewriting it."""
        if record and path != self.path:
            self.history = self.history[:self.history_at + 1] + [path]
            self.history_at = len(self.history) - 1
        self.path = path
        self.page = 0
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.render()

    def go_back(self):
        if self.history_at > 0:
            self.history_at -= 1
            self.navigate(self.history[self.history_at], record=False)

    def go_forward(self):
        if self.history_at + 1 < len(self.history):
            self.history_at += 1
            self.navigate(self.history[self.history_at], record=False)

    def _route_label(self, path):
        if not path:
            return tr("All cartons")
        return path[-1] if path[-1] is not None else tr("Unassigned")

    def _sync_route_buttons(self):
        back = self.history_at > 0
        forward = self.history_at + 1 < len(self.history)
        self.back_btn.setEnabled(back)
        self.forward_btn.setEnabled(forward)
        self.back_btn.setToolTip(
            tr("Back to {p0}", p0=self._route_label(self.history[self.history_at - 1]))
            if back else tr("Nothing to go back to"))
        self.forward_btn.setToolTip(
            tr("Forward to {p0}", p0=self._route_label(self.history[self.history_at + 1]))
            if forward else tr("Nothing to go forward to"))

    def _filter_changed(self):
        self.page = 0
        self.render()

    def _change_page(self, delta):
        self.page += delta
        self.render()

    def render(self):
        while self.breadcrumbs.count():
            item = self.breadcrumbs.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for index in range(len(self.path) + 1):
            if index:
                self.breadcrumbs.addWidget(QLabel("›"))
            label = tr("All cartons") if index == 0 else self.path[index - 1]
            button = QPushButton(label if label is not None else tr("Unassigned"))
            button.setObjectName("ghostBtn")
            button.setToolTip(label if label is not None else tr("Unassigned"))
            # index 0 is "everything"; crumb n names the level it stands in.
            button.setIcon(level_icon(LEVELS[index - 1] if index else "carton", 14))
            button.setIconSize(QSize(14, 14))
            button.clicked.connect(lambda checked=False, p=self.path[:index]: self.navigate(p))
            self.breadcrumbs.addWidget(button)
        self.breadcrumbs.addStretch()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.cards = []
        node = self.root
        for serial in self.path:
            node = node.children[serial]
        query = self.search.text().casefold()
        children = [child for serial, child in node.children.items()
                    if query in (serial if serial is not None else str(tr("Unassigned"))).casefold()]
        children.sort(key=lambda child: (child.path[-1] is None, child.path[-1] or ""))
        pages = max(1, (len(children) + self.page_size - 1) // self.page_size)
        self.page = max(0, min(self.page, pages - 1))
        self._set_summary(tr("{p0} items · {p1} saved rows", p0=len(children), p1=node.rows))
        if not children:
            empty = QLabel(tr("No containers found. Adjust the filters or search."))
            empty.setObjectName("dialogHint")
            empty.setAlignment(Qt.AlignCenter)
            self.cards.append(empty)
        for child in children[self.page * self.page_size:(self.page + 1) * self.page_size]:
            self.cards.append(self._card(child))
        self._reflow()
        self.page_label.setText(tr("Page {p0} of {p1}", p0=self.page + 1, p1=pages))
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page + 1 < pages)
        self._sync_route_buttons()

    def _card(self, node):
        level = LEVELS[len(node.path) - 1]
        serial = node.path[-1]
        card = QFrame()
        card.setObjectName("containerCard")
        # The stylesheet paints the top rule in this level's colour (style.css).
        card.setProperty("level", level)
        box = QVBoxLayout(card)
        card.setFixedHeight(CARD_HEIGHT)
        card.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(2)
        label = QLabel(tr(level.capitalize()))
        label.setObjectName("containerLevel")
        mark = QLabel()
        mark.setObjectName("levelMark")
        mark.setPixmap(level_mark(level, 18))
        mark.setFixedSize(18, 18)
        # A QLabel, not a button: the first QPushButton on a card is its Open,
        # and the first #linkBtn is Rename. Both are relied on elsewhere.
        heading = QHBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(mark)
        heading.addWidget(label)
        heading.addStretch()
        box.addLayout(heading)
        details = QHBoxLayout()
        details.setSpacing(8)
        image_path = self.avatars.resolve(level, node.products)
        if image_path:
            pixmap = avatar_pixmap(image_path)
            if not pixmap.isNull():
                avatar = AvatarLabel()
                avatar.setObjectName("productAvatar")
                avatar.setFixedSize(44, 44)
                avatar.setAlignment(Qt.AlignCenter)
                avatar.setPixmap(pixmap)
                avatar.setToolTip("\n".join(sorted(node.products)))
                avatar.setAccessibleName("\n".join(sorted(node.products)))
                avatar.clicked.connect(
                    lambda p=image_path, name="\n".join(sorted(node.products)): self._show_image(p, name)
                )
                details.addWidget(avatar)
        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(serial if serial is not None else tr("Unassigned"))
        name.setTextFormat(Qt.PlainText)
        name.setWordWrap(False)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        name.setToolTip(serial if serial is not None else tr("Unassigned"))
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name.setObjectName("containerSerial")
        info.addWidget(name)
        count = QLabel(tr("{p0} saved rows", p0=node.rows))
        if level != "unit":
            count.setText(tr("{p0} inside · {p1} saved rows", p0=len(node.children), p1=node.rows))
        count.setObjectName("dialogHint")
        info.addWidget(count)
        details.addLayout(info, 1)
        box.addLayout(details, 1)
        actions = QHBoxLayout()
        open_button = QPushButton(tr("View records") if level == "unit" else tr("Open box"))
        open_button.setObjectName("searchBtn")
        open_button.clicked.connect(
            lambda checked=False, p=node.path: self.records_requested.emit(p)
            if len(p) == 4 else self.navigate(p)
        )
        actions.addWidget(open_button)
        if level != "unit":
            records = QPushButton(tr("View records"))
            records.setObjectName("ghostBtn")
            records.clicked.connect(lambda checked=False, p=node.path: self.records_requested.emit(p))
            actions.addWidget(records)
        box.addLayout(actions)
        rename = QPushButton(tr("Rename"))
        rename.setObjectName("linkBtn")
        rename.setEnabled(self.is_admin and serial is not None)
        if serial is None:
            rename.setToolTip(tr("Unassigned groups have no serial to rename."))
        elif not self.is_admin:
            rename.setToolTip(tr("Only admins can rename containers"))
        rename.clicked.connect(lambda checked=False, l=level, s=serial: self.rename_requested.emit(l, s))
        heading.addWidget(rename)
        if level != "unit":
            # After Rename, so the first "linkBtn" on a card is still Rename. Units are
            # deleted from the records grid, so their cards carry no Delete link.
            delete = QPushButton(tr("Delete"))
            delete.setObjectName("linkBtn")
            delete.setProperty("action", "delete")
            delete.setEnabled(self.is_admin and serial is not None)
            if serial is None:
                delete.setToolTip(tr("Unassigned groups have no serial to delete."))
            elif not self.is_admin:
                delete.setToolTip(tr("Only admins can delete containers"))
            delete.clicked.connect(lambda checked=False, l=level, s=serial: self.delete_requested.emit(l, s))
            heading.addWidget(delete)
        return card

    def _show_image(self, path, product_name):
        for preview in self.findChildren(ImagePreview):
            if preview.image_path == path and preview.isVisible():
                preview.raise_()
                preview.activateWindow()
                return
        preview = ImagePreview(path, product_name, self)
        preview.show()

    def _reflow(self):
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for column in range(self._grid_columns):
            self.grid.setColumnStretch(column, 1)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // self._grid_columns, index % self._grid_columns)

    def _fit_page(self):
        columns = max(1, min(5, (self.inner.width() + GRID_GAP) // (CARD_WIDTH + GRID_GAP)))
        rows = max(1, (self.inner.height() + GRID_GAP) // (CARD_HEIGHT + GRID_GAP))
        capacity = min(PAGE_SIZE, columns * rows)
        if (columns, capacity) != (self._grid_columns, self.page_size):
            first_item = self.page * self.page_size
            self._grid_columns = columns
            self.page_size = capacity
            self.page = first_item // capacity
            self.render()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize and watched is self.inner:
            self._resize_timer.start(0)
        return super().eventFilter(watched, event)
