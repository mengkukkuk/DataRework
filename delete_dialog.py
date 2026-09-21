"""Delete a container after listing everything inside it.

Pick a level, then a container (from the list, or by scanning its serial); the
dialog immediately lists what is inside it and what deleting would remove. Nothing
is deleted here: accepting only hands the reviewed selection back, and the caller
asks once more before touching the database.

No container is ever pre-selected. The rename dialog offers the first serial as a
starting point; here that would put a destructive button one click from a
container the user never chose.
"""

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
)

import db
from i18n import tr
from i18n_widgets import QLabel, QPushButton, QComboBox, QLineEdit, QWidget, QDialog

# Outermost first, like the rename dialog's rail. Units are deleted from the grid.
LEVEL_ORDER = ("carton", "inner", "display")

# Left indent added per level of nesting in the "inside" list.
INDENT = 20


def _field_label(text):
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


class DeleteContainerDialog(QDialog):
    """Pick a container, review everything inside it, then confirm."""

    def __init__(self, parent=None, table="filling_product_logs", level="carton", serial=""):
        super().__init__(parent)
        self.setWindowTitle(tr('Delete container'))
        self.setMinimumSize(560, 480)
        self.resize(640, 640)  # room for the list: a carton can hold ~130 units

        self._table = table
        self._level = level if level in LEVEL_ORDER else "carton"
        self._preview = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._update_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(6)

        title = QLabel(tr('Delete container'))
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        blurb = QLabel(tr(
            'Pick a carton, inner or display. It is deleted together with everything inside it: '
            'its saved rows and links. Nothing is deleted until you confirm.'
        ))
        blurb.setObjectName("dialogHint")
        blurb.setWordWrap(True)
        root.addWidget(blurb)
        root.addSpacing(12)

        root.addWidget(_field_label(tr('Level')))
        root.addWidget(self._build_level_rail(), alignment=Qt.AlignLeft)
        root.addSpacing(10)

        root.addWidget(_field_label(tr('Serial')))
        root.addWidget(self._build_serial_box())
        root.addSpacing(10)

        root.addWidget(_field_label(tr('Inside this container')))
        root.addWidget(self._build_list(), stretch=1)

        self.summary = QLabel("")
        self.summary.setObjectName("dialogHint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        self.emptied_label = QLabel("")
        self.emptied_label.setObjectName("dialogHint")
        self.emptied_label.setWordWrap(True)
        root.addWidget(self.emptied_label)
        root.addSpacing(12)

        root.addLayout(self._build_buttons())

        self._reload_serials(preferred=serial)

    # -- construction ------------------------------------------------------

    def _build_level_rail(self):
        frame = QFrame()
        frame.setObjectName("levelSeg")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self._level_buttons = {}
        group = QButtonGroup(frame)
        group.setExclusive(True)
        for name in LEVEL_ORDER:
            button = QPushButton(tr(name.capitalize()))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, n=name: self.set_level(n))
            group.addButton(button)
            layout.addWidget(button)
            self._level_buttons[name] = button

        self._level_buttons[self._level].setChecked(True)
        return frame

    def _build_serial_box(self):
        self.serial_combo = QComboBox()
        self.serial_combo.setObjectName("serialOld")
        self.serial_combo.setEditable(True)
        self.serial_combo.setLineEdit(QLineEdit(self.serial_combo))
        self.serial_combo.setInsertPolicy(QComboBox.NoInsert)
        self.serial_combo.setCompleter(None)
        self.serial_combo.lineEdit().setPlaceholderText(tr('Scan or type the serial to delete'))
        self.serial_combo.lineEdit().installEventFilter(self)
        self.serial_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.serial_combo.currentTextChanged.connect(self._on_serial_changed)
        return self.serial_combo

    def _build_list(self):
        scroll = QScrollArea()
        scroll.setObjectName("childScroll")
        scroll.setWidgetResizable(True)

        host = QWidget()
        host.setObjectName("childScrollInner")
        self._list_layout = QVBoxLayout(host)
        self._list_layout.setContentsMargins(0, 0, 8, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)

        scroll.setWidget(host)
        return scroll

    def _build_buttons(self):
        row = QHBoxLayout()
        row.addStretch(1)

        cancel = QPushButton(tr('Cancel'))
        cancel.setObjectName("ghostBtn")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)

        # Neither button is the default, so Enter can never confirm the delete.
        self.delete_btn = QPushButton(tr('Delete'))
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.setAutoDefault(False)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.accept)

        row.addWidget(cancel)
        row.addWidget(self.delete_btn)
        return row

    def _row(self, child):
        frame = QFrame()
        frame.setObjectName("childRow")
        row = QHBoxLayout(frame)
        row.setContentsMargins(6 + INDENT * (child["depth"] - 1), 3, 6, 3)
        row.setSpacing(10)

        name = QLabel(child["serial_no"])
        name.setObjectName("insideSerial")
        name.setTextFormat(Qt.PlainText)

        if child["level"] == "unit":
            detail = tr('unit')
        elif child["children"]:
            detail = tr('{p0} inside', p0=child["children"])
        else:
            detail = tr('empty')
        count = QLabel(detail)
        count.setObjectName("childCount")
        count.setMinimumWidth(64)
        count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        row.addWidget(name, 1)
        row.addWidget(count)
        return frame

    # -- behaviour ---------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._focus_serial_box)

    def _focus_serial_box(self):
        if not self.isVisible():
            return
        edit = self.serial_combo.lineEdit()
        edit.setFocus(Qt.OtherFocusReason)
        edit.selectAll()

    def eventFilter(self, watched, event):
        if (watched is self.serial_combo.lineEdit() and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            # Scanners end a scan with CR/LF: show the container, never confirm it.
            self._preview_timer.stop()
            self._update_preview()
            return True
        return super().eventFilter(watched, event)

    def set_level(self, name):
        if name not in LEVEL_ORDER or name == self._level:
            return
        self._level = name
        self._level_buttons[name].setChecked(True)
        self._reload_serials()
        self._focus_serial_box()

    def _reload_serials(self, preferred=""):
        error = ""
        try:
            serials = db.container_serials(self._level)
        except Exception as exc:  # shown in the summary line, not a second popup
            serials, error = [], str(exc)

        self.serial_combo.blockSignals(True)
        self.serial_combo.clear()
        self.serial_combo.addItems(serials)
        if preferred:
            if preferred not in serials:
                self.serial_combo.addItem(preferred)
            self.serial_combo.setCurrentText(preferred)
        else:
            self.serial_combo.setCurrentIndex(-1)
            self.serial_combo.setCurrentText("")
        self.serial_combo.blockSignals(False)

        self._preview_timer.stop()
        self._update_preview()
        if error:
            self.summary.setText(error)

    def _on_serial_changed(self, _text=None):
        # Typing or picking: what is on screen no longer matches the serial, so the
        # confirm button goes off until the new container has been looked up.
        self._preview = None
        self.delete_btn.setEnabled(False)
        self._preview_timer.start()

    def _update_preview(self):
        serial = self.serial()
        self._preview = None
        self._show_children([])
        self.emptied_label.setText("")

        if not serial:
            self.summary.setText(
                tr('Scan or pick the serial to delete. Everything inside it is listed here first.'))
        else:
            try:
                preview = db.container_delete_preview(self._level, serial, table=self._table)
            except Exception as exc:  # ContainerDeleteError, or the database being away
                self.summary.setText(str(exc))
            else:
                self._preview = preview
                self._show_children(preview["children"])
                self.summary.setText(tr(
                    '{p0} unit(s) · {p1} saved row(s) · {p2} link(s) will be deleted.',
                    p0=preview["units"], p1=preview["rows"], p2=preview["edges"]))
                if preview["emptied"]:
                    names = tr(', ').join(
                        [tr(item["level"]) + " " + item["serial_no"] for item in preview["emptied"]])
                    self.emptied_label.setText(
                        tr('Also removed, because they would be left empty: {p0}.', p0=names))

        self.delete_btn.setEnabled(self._preview is not None)

    def _show_children(self, children):
        while self._list_layout.count() > 1:  # the last item is the trailing stretch
            widget = self._list_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # off the dialog now, not whenever the loop runs
                widget.deleteLater()
        for index, child in enumerate(children):
            self._list_layout.insertWidget(index, self._row(child))

    @property
    def level(self):
        return self._level

    def serial(self):
        return self.serial_combo.currentText().strip()

    def preview(self):
        """The preview the user reviewed; hand it to delete_container(expected=...)."""
        return self._preview
