"""Two-stage container rename.

Stage 1 (RenameContainerDialog) renames one container. Stage 2
(ChildRelabelDialog) then lists everything that container holds, so the user can
carry the new scheme down to the children they choose.

They are separate windows on purpose: stage 1 is a single irreversible write the
user must see the blast radius of, and stage 2 only makes sense once that write
has landed and the children can be listed under the new name.
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
from i18n import tr, column_label, language
from i18n_widgets import (QLabel, QPushButton, QCheckBox, QComboBox, QGroupBox,
                          QLineEdit, QWidget, QMainWindow, QDialog, QMessageBox, LanguageToggle)

# Outermost first, so the rail reads as the containment order it is rather than
# an alphabetical list.
LEVEL_ORDER = ("carton", "inner", "display", "unit")

# ASCII keeps this separator available even on minimal font installations.
ARROW = ">"


def _field_label(text):
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


def suggest_child_serial(child_serial, old_parent, new_parent):
    """What the child would be called if it follows its parent's rename.

    Children are usually named off the container they sit in, so substituting
    the parent's serial inside the child's is right far more often than not.
    When it is not a substring there is nothing to infer, and the child keeps
    its name until the user types one.
    """
    if old_parent and old_parent in child_serial:
        return child_serial.replace(old_parent, new_parent)
    return child_serial


class RenameContainerDialog(QDialog):
    """Pick a level, pick a container, give it a new serial."""

    def __init__(self, parent=None, level="carton", serial="", scan_ready=False):
        super().__init__(parent)
        self.setWindowTitle(tr('Rename serial'))
        self.setMinimumWidth(540)

        self._level = level if level in LEVEL_ORDER else "carton"
        self._previews = {}
        self._last_old = ""
        self._scan_ready = scan_ready
        self._prefilled = bool(serial)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._update_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(6)

        title = QLabel(tr('Rename serial'))
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        blurb = QLabel(
            tr('Rename a carton, inner, display or unit serial. Every matching saved row and link will be updated.')
        )
        blurb.setObjectName("dialogHint")
        blurb.setWordWrap(True)
        root.addWidget(blurb)
        root.addSpacing(14)

        root.addWidget(_field_label(tr('Level')))
        root.addWidget(self._build_level_rail(), alignment=Qt.AlignLeft)
        root.addSpacing(14)

        root.addWidget(_field_label(tr('Serial')))
        root.addLayout(self._build_slab_pair())

        self.hint = QLabel("")
        self.hint.setObjectName("dialogHint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)
        root.addSpacing(16)

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
        self._level_group = QButtonGroup(frame)
        self._level_group.setExclusive(True)
        for name in LEVEL_ORDER:
            btn = QPushButton(tr(name.capitalize()))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, n=name: self.set_level(n))
            self._level_group.addButton(btn)
            layout.addWidget(btn)
            self._level_buttons[name] = btn

        self._level_buttons[self._level].setChecked(True)
        return frame

    def _build_slab_pair(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        self.old_combo = QComboBox()
        self.old_combo.setObjectName("serialOld")
        self.old_combo.setEditable(True)
        self.old_combo.setLineEdit(QLineEdit(self.old_combo))
        self.old_combo.setInsertPolicy(QComboBox.NoInsert)
        self.old_combo.setCompleter(None)
        self.old_combo.lineEdit().setPlaceholderText(tr('Scan or type the current serial'))
        self.old_combo.lineEdit().installEventFilter(self)
        self.old_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.old_combo.currentTextChanged.connect(self._on_old_changed)

        arrow = QLabel(ARROW)
        arrow.setObjectName("serialArrow")

        self.new_edit = QLineEdit()
        self.new_edit.setObjectName("serialNew")
        self.new_edit.setPlaceholderText(tr('new serial'))
        self.new_edit.installEventFilter(self)
        self.new_edit.textChanged.connect(self._refresh_state)

        row.addWidget(self.old_combo, 1)
        row.addWidget(arrow)
        row.addWidget(self.new_edit, 1)
        return row

    def _build_buttons(self):
        row = QHBoxLayout()
        row.addStretch(1)

        cancel = QPushButton(tr('Cancel'))
        cancel.setObjectName("ghostBtn")
        cancel.clicked.connect(self.reject)

        self.confirm_btn = QPushButton(tr('Rename'))
        self.confirm_btn.setObjectName("primaryBtn")
        self.confirm_btn.setAutoDefault(False)
        cancel.setAutoDefault(False)
        self.confirm_btn.clicked.connect(self.accept)

        row.addWidget(cancel)
        row.addWidget(self.confirm_btn)
        return row

    # -- behaviour ---------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._focus_scan_input)

    def _focus_scan_input(self):
        if not self.isVisible():
            return
        edit = self.new_edit if self._prefilled else self.old_combo.lineEdit()
        edit.setFocus(Qt.OtherFocusReason)
        edit.selectAll()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if watched is self.old_combo.lineEdit():
                self._preview_timer.stop()
                self._update_preview()
                if self.old_combo.currentText().strip():
                    self.new_edit.setFocus(Qt.OtherFocusReason)
                    self.new_edit.selectAll()
                return True
            if watched is self.new_edit:
                # Keyboard-wedge scanners commonly append CR/LF. Never let
                # either terminator submit the dialog or a subsequent confirmation.
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
        self._prefilled = False
        self._focus_scan_input()

    def _reload_serials(self, preferred=""):
        error = ""
        try:
            serials = db.container_serials(self._level)
        except Exception as exc:  # shown in the hint line, not a second popup
            serials, error = [], str(exc)

        self.old_combo.blockSignals(True)
        self.old_combo.clear()
        self.old_combo.addItems(serials)
        if preferred:
            if preferred not in serials:
                self.old_combo.addItem(preferred)
            self.old_combo.setCurrentText(preferred)
        elif serials and not self._scan_ready:
            self.old_combo.setCurrentIndex(0)
        else:
            self.old_combo.setCurrentIndex(-1)
            self.old_combo.setCurrentText("")
        self.old_combo.blockSignals(False)

        self._on_old_changed(self.old_combo.currentText())
        if error:
            self.hint.setText(error)

    def _on_old_changed(self, text):
        # Prefilled with the old serial, because the common case is changing a
        # digit or two -- an edit, not a retype. Anything the user has actually
        # typed is left alone.
        if not self.new_edit.text().strip() or self.new_edit.text() == self._last_old:
            self.new_edit.setText(text)
        self._last_old = text
        self._refresh_state()

    def _preview(self, level, serial):
        key = (level, serial)
        if key not in self._previews:
            try:
                self._previews[key] = db.container_rename_preview(level, serial)
            except Exception:
                self._previews[key] = None
        return self._previews[key]

    def _refresh_state(self):
        old, new = self.values()
        self.confirm_btn.setEnabled(bool(old and new and new != old))

        if self._scan_ready:
            self._preview_timer.start()
        else:
            self._update_preview()

    def _update_preview(self):
        old, _new = self.values()

        if not old:
            self.hint.setText(tr('Scan the current serial, then scan or type the new serial. Click Rename when ready.'))
            return

        preview = self._preview(self._level, old)
        if preview is None:
            self.hint.setText("")
        else:
            self.hint.setText(
                tr('{p0} row(s) and {p1} link(s) name "{p2}". All of them will be rewritten.', p0=preview["rows"], p1=preview["edges"], p2=old)
            )

    def values(self):
        return self.old_combo.currentText().strip(), self.new_edit.text().strip()

    @property
    def level(self):
        return self._level


class ChildRelabelDialog(QDialog):
    """Stage 2 -- carry the new scheme down to the children the user ticks."""

    def __init__(self, parent, parent_level, old_parent, new_parent, children):
        super().__init__(parent)
        self.setWindowTitle(tr('Rename children'))
        self.setMinimumSize(620, 440)

        self._rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(6)

        title = QLabel(tr('Inside {p0} {p1}', p0=tr(parent_level), p1=new_parent))
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        child_level = children[0]["level"] if children else "child"
        blurb = QLabel(
            tr('{p0} {p1}(s) still carry their old serials. Tick the ones that should follow the rename and leave the rest as they are.', p0=len(children), p1=tr(child_level))
        )
        blurb.setObjectName("dialogHint")
        blurb.setWordWrap(True)
        root.addWidget(blurb)
        root.addSpacing(10)

        root.addLayout(self._build_select_row())
        root.addWidget(self._build_list(old_parent, new_parent, children), stretch=1)
        root.addSpacing(12)
        root.addLayout(self._build_buttons())
        self._refresh_state()

    def _build_select_row(self):
        row = QHBoxLayout()
        for text, checked in (("Select all", True), ("Select none", False)):
            btn = QPushButton(tr(text))
            btn.setObjectName("linkBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, v=checked: self._set_all(v))
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _build_list(self, old_parent, new_parent, children):
        scroll = QScrollArea()
        scroll.setObjectName("childScroll")
        scroll.setWidgetResizable(True)

        inner = QWidget()
        inner.setObjectName("childScrollInner")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(2)
        for child in children:
            layout.addWidget(self._build_row(child, old_parent, new_parent))
        layout.addStretch(1)

        scroll.setWidget(inner)
        return scroll

    def _build_row(self, child, old_parent, new_parent):
        frame = QFrame()
        frame.setObjectName("childRow")
        row = QHBoxLayout(frame)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(10)

        check = QCheckBox()
        check.setChecked(True)

        old = QLabel(child["serial_no"])
        old.setObjectName("serialOld")

        arrow = QLabel(ARROW)
        arrow.setObjectName("serialArrow")

        new = QLineEdit(suggest_child_serial(child["serial_no"], old_parent, new_parent))
        new.setObjectName("serialNew")
        new.textChanged.connect(self._refresh_state)

        count = QLabel(tr('{p0} inside', p0=child["children"]) if child["children"] else tr('empty'))
        count.setObjectName("childCount")
        count.setMinimumWidth(64)
        count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        check.toggled.connect(new.setEnabled)
        check.toggled.connect(self._refresh_state)

        row.addWidget(check)
        row.addWidget(old, 1)
        row.addWidget(arrow)
        row.addWidget(new, 1)
        row.addWidget(count)

        self._rows.append((check, child, new))
        return frame

    def _build_buttons(self):
        row = QHBoxLayout()
        self.warning = QLabel("")
        self.warning.setObjectName("dialogHint")
        self.warning.setWordWrap(True)
        row.addWidget(self.warning, 1)

        skip = QPushButton(tr('Skip'))
        skip.setObjectName("ghostBtn")
        skip.clicked.connect(self.reject)

        self.apply_btn = QPushButton(tr('Apply'))
        self.apply_btn.setObjectName("primaryBtn")
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self.accept)

        row.addWidget(skip)
        row.addWidget(self.apply_btn)
        return row

    def _set_all(self, checked):
        for check, _child, _edit in self._rows:
            check.setChecked(checked)

    def _refresh_state(self):
        renames = self.renames()
        self.apply_btn.setText(tr('Apply {p0} change(s)', p0=len(renames)) if renames else tr('Apply'))

        # Caught here rather than at the database, where the batch is atomic and
        # one clash would discard every other edit the user just made.
        new_names = [new for _level, _old, new in renames]
        clashing = sorted({n for n in new_names if new_names.count(n) > 1})
        self.warning.setText(
            tr('Two children would share {p0}.', p0=', '.join(clashing)) if clashing else ""
        )
        self.apply_btn.setEnabled(bool(renames) and not clashing)

    def renames(self):
        """[(level, old, new)] for every ticked row that actually changes."""
        out = []
        for check, child, edit in self._rows:
            new = edit.text().strip()
            if check.isChecked() and new and new != child["serial_no"]:
                out.append((child["level"], child["serial_no"], new))
        return out
