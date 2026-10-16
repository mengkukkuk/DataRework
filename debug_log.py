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

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QHBoxLayout

from i18n import tr
from i18n_widgets import QCheckBox, QDialog, QLabel, QPushButton

MAX_ENTRIES = 500
_DETAILS_KEY = "log_show_details"


def _settings():
    return QSettings("DataRework", "ProductionRework")


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

    def as_text(self, details=True):
        """Render the log; `details=False` keeps only the one-line messages."""
        blocks = []
        for entry in self.entries:
            blocks.append(f"[{entry['time']}] {entry['level']}  {entry['message']}")
            if details and entry["detail"]:
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
        title = QLabel(tr('The most recent errors. Newest last.'))
        title.setObjectName('dialogTitle')
        title.setWordWrap(True)
        layout.addWidget(title)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setObjectName('logView')
        layout.addWidget(self.view, 1)

        buttons = QHBoxLayout()
        # Operators normally only need the message; the traceback is for whoever
        # debugs it, so it stays hidden until asked for (and the choice sticks).
        self.details_check = QCheckBox(tr('Show technical details'))
        self.details_check.setChecked(
            _settings().value(_DETAILS_KEY, False, type=bool))
        self.details_check.toggled.connect(self._on_details_toggled)
        buttons.addWidget(self.details_check)
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

    def _on_details_toggled(self, checked):
        _settings().setValue(_DETAILS_KEY, checked)
        self._refresh()

    def _refresh(self):
        details = self.details_check.isChecked()
        # Messages read best wrapped; tracebacks keep their column alignment.
        self.view.setLineWrapMode(
            QPlainTextEdit.NoWrap if details else QPlainTextEdit.WidgetWidth)
        scrollbar = self.view.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.view.setPlainText(
            LOG.as_text(details) or str(tr('No errors recorded yet.')))
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _copy(self):
        # Always copy the full detail: a pasted bug report needs the traceback
        # even when the operator was only reading the short messages.
        QApplication.clipboard().setText(LOG.as_text(details=True))
