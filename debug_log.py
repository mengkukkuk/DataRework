"""In-memory error log and the non-modal window that shows it.

The status bar deliberately shows one short line, so the detail behind a
failure -- which serial, which table, the traceback -- used to be lost unless
the operator happened to be running from a console. LOG keeps the last few
hundred entries in memory so the Log button can show the full text after the
fact.

Nothing is written to disk: these entries quote serials and table names, and
the GUI already runs against the live database.
"""
import datetime
import traceback
from collections import deque

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QHBoxLayout

from i18n import tr
from i18n_widgets import QDialog, QLabel, QPushButton

MAX_ENTRIES = 500


class _Log(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.entries = deque(maxlen=MAX_ENTRIES)

    def add(self, message, exc=None, level="ERROR"):
        """Record one line. `exc` adds its traceback as indented detail."""
        detail = ""
        if exc is not None:
            detail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).rstrip()
        self.entries.append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": str(message),
            "detail": detail,
        })
        self.changed.emit()

    def clear(self):
        self.entries.clear()
        self.changed.emit()

    def as_text(self):
        blocks = []
        for entry in self.entries:
            blocks.append(f"[{entry['time']}] {entry['level']}  {entry['message']}")
            if entry["detail"]:
                blocks.extend(f"    {line}" for line in entry["detail"].splitlines())
        return "\n".join(blocks)


LOG = _Log()


class LogWindow(QDialog):
    """Non-modal, so the operator can retry the failing action while reading it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Error log'))
        self.setWindowFlag(Qt.Window)
        self.setMinimumSize(520, 320)
        self.resize(760, 460)

        layout = QVBoxLayout(self)
        title = QLabel(tr('Full details of the most recent errors. Newest last.'))
        title.setObjectName('dialogTitle')
        title.setWordWrap(True)
        layout.addWidget(title)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setObjectName('logView')
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.view, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for label, slot in ((tr('Copy'), self._copy),
                            (tr('Clear'), LOG.clear),
                            (tr('Close'), self.close)):
            button = QPushButton(label)
            button.setObjectName('ghostBtn')
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        LOG.changed.connect(self._refresh)
        self._refresh()

    def _refresh(self):
        scrollbar = self.view.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.view.setPlainText(LOG.as_text() or str(tr('No errors recorded yet.')))
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _copy(self):
        self.view.selectAll()
        self.view.copy()
        cursor = self.view.textCursor()
        cursor.clearSelection()
        self.view.setTextCursor(cursor)
