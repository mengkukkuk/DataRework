"""Display settings behind the header's gear button.

Language and theme used to sit in the header as two small EN/TH and
Dark/Light toggles. They change rarely, so they live here instead, with
full names and a line saying what each one does. Every choice applies the
moment it is clicked and is remembered, so there is no Save/Cancel step.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QVBoxLayout

from i18n import language, tr
from i18n_widgets import QDialog, QLabel, QPushButton

# Each language is named in its own script so it can be found whatever the
# current language is.
LANGUAGE_NAMES = (("en", "English"), ("th", "ไทย"))


class SettingsDialog(QDialog):
    def __init__(self, parent, theme, on_theme):
        super().__init__(parent)
        self.setWindowTitle(tr('Settings'))
        self.setMinimumWidth(420)
        self._on_theme = on_theme

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(6)

        title = QLabel(tr('Settings'))
        title.setObjectName("dialogTitle")
        root.addWidget(title)
        hint = QLabel(tr('Changes apply right away and are remembered on this computer.'))
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addSpacing(10)

        self.language_buttons = self._add_section(
            root, tr('Language'), tr('Language of menus, buttons and messages.'),
            LANGUAGE_NAMES, language.set)
        root.addSpacing(12)
        self.theme_buttons = self._add_section(
            root, tr('Appearance'), tr('Dark or light colours for the whole window.'),
            (("dark", tr('Dark')), ("light", tr('Light'))), self._set_theme)

        root.addSpacing(16)
        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton(tr('Close'))
        close.setObjectName("ghostBtn")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

        self.theme_buttons[theme].setChecked(True)
        language.changed.connect(self._sync_language)
        self._sync_language()

    def _add_section(self, root, heading, description, options, on_pick):
        label = QLabel(heading)
        label.setObjectName("fieldLabel")
        root.addWidget(label)
        note = QLabel(description)
        note.setObjectName("dialogHint")
        note.setWordWrap(True)
        root.addWidget(note)

        frame = QFrame()
        frame.setObjectName("settingsSeg")
        row = QHBoxLayout(frame)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        group = QButtonGroup(frame)
        group.setExclusive(True)
        buttons = {}
        for key, text in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: on_pick(k))
            group.addButton(button)
            row.addWidget(button, 1)
            buttons[key] = button
        root.addWidget(frame)
        return buttons

    def _set_theme(self, name):
        self.theme_buttons[name].setChecked(True)
        self._on_theme(name)

    def _sync_language(self):
        self.language_buttons[language.code].setChecked(True)
