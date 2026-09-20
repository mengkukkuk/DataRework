"""Qt widgets that retranslate explicitly marked UI text, never user data."""
from PySide6 import QtWidgets as QtW
from PySide6.QtCore import QSignalBlocker

from i18n import CATALOGS, Message, language, tr


class Localized:
    def __init__(self, *args, **kwargs):
        self._messages = {}
        self._items = {}
        super().__init__(*args, **kwargs)
        if args and isinstance(args[0], Message):
            prop = "title" if isinstance(self, QtW.QGroupBox) else "text"
            self._messages[prop] = args[0]
        language.changed.connect(self._retranslate)

    def _set_message(self, prop, value):
        self._messages.pop(prop, None)
        if isinstance(value, Message):
            self._messages[prop] = value
            value = value.render()
        getattr(super(), "set" + prop[0].upper() + prop[1:])(value)

    def setText(self, value):
        self._set_message("text", value)

    def setTitle(self, value):
        self._set_message("title", value)

    def setWindowTitle(self, value):
        self._set_message("windowTitle", value)

    def setToolTip(self, value):
        self._set_message("toolTip", value)

    def setPlaceholderText(self, value):
        self._set_message("placeholderText", value)

    def _retranslate(self):
        blocker = QSignalBlocker(self)
        for prop, message in self._messages.items():
            getattr(super(), "set" + prop[0].upper() + prop[1:])(message.render())
        for index, message in self._items.items():
            self.setItemText(index, message.render())
        del blocker


class QLabel(Localized, QtW.QLabel):
    pass


class QPushButton(Localized, QtW.QPushButton):
    def sizeHint(self):
        size = super().sizeHint()
        message = self._messages.get("text")
        if message is not None:
            # Reserve the widest translation without changing the active language.
            metrics = self.fontMetrics()
            widest = max(metrics.size(0, message.render(code)).width() for code in CATALOGS)
            size.setWidth(size.width() + max(0, widest - metrics.size(0, self.text()).width()))
        return size

    def minimumSizeHint(self):
        return self.sizeHint()


class QCheckBox(Localized, QtW.QCheckBox):
    pass


class QGroupBox(Localized, QtW.QGroupBox):
    pass


class QLineEdit(Localized, QtW.QLineEdit):
    pass


class QWidget(Localized, QtW.QWidget):
    pass


class QMainWindow(Localized, QtW.QMainWindow):
    pass


class QDialog(Localized, QtW.QDialog):
    pass


class QComboBox(Localized, QtW.QComboBox):
    def addItem(self, text, userData=None):
        if isinstance(text, Message):
            self._items[self.count()] = text
            text = text.render()
        super().addItem(text, userData)

    def clear(self):
        self._items.clear()
        super().clear()


class QMessageBox(QtW.QMessageBox):
    @staticmethod
    def question(parent, title, text, buttons, defaultButton):
        dialog = QtW.QMessageBox(QtW.QMessageBox.Question, str(title), str(text), buttons, parent)
        dialog.setDefaultButton(defaultButton)
        for role, label in ((QtW.QMessageBox.Yes, "Yes"), (QtW.QMessageBox.No, "No")):
            button = dialog.button(role)
            if button:
                button.setText(tr(label))
        return dialog.exec()


class LanguageToggle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("themeToggle")
        self.setAccessibleName(tr("Language"))
        layout = QtW.QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.group = QtW.QButtonGroup(self)
        self.buttons = {}
        for code in ("en", "th"):
            button = QtW.QPushButton(code.upper())
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, code=code: language.set(code))
            self.group.addButton(button)
            self.buttons[code] = button
            layout.addWidget(button)
        language.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        self.buttons[language.code].setChecked(True)
        self.setAccessibleName(tr("Language"))
