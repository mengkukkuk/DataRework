import psycopg2
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
)

import db
from i18n import tr, column_label, language
from i18n_widgets import (QLabel, QPushButton, QCheckBox, QComboBox, QGroupBox,
                          QLineEdit, QWidget, QMainWindow, QDialog, QMessageBox, LanguageToggle)


class LoginWindow(QWidget):
    login_succeeded = Signal(str, str)  # username, permission

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('Login'))
        self.resize(360, 220)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(tr('Username'))
        self.username_input.setMinimumWidth(280)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(tr('Password'))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumWidth(280)

        self.login_button = QPushButton(tr('Login'))

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(LanguageToggle(self))
        layout.addWidget(QLabel(tr('Username')))
        layout.addWidget(self.username_input)
        layout.addWidget(QLabel(tr('Password')))
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        layout.addWidget(self.error_label)

        self.login_button.clicked.connect(self._attempt_login)
        self.username_input.returnPressed.connect(self._attempt_login)
        self.password_input.returnPressed.connect(self._attempt_login)

    def _attempt_login(self):
        username = self.username_input.text()
        password = self.password_input.text()

        try:
            permission = db.authenticate(username, password)
        except psycopg2.OperationalError as exc:
            print(f"Database connection error: {exc}")
            self._show_error(tr('Unable to reach the database'))
            return

        if permission is not None:
            self.login_succeeded.emit(username, permission)
        else:
            self._show_error(tr('Invalid username or password'))
            self.password_input.clear()

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()
