import psycopg2
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import db


class LoginWindow(QWidget):
    login_succeeded = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.login_button = QPushButton("Login")

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.hide()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Username"))
        layout.addWidget(self.username_input)
        layout.addWidget(QLabel("Password"))
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
            valid = db.verify_user(username, password)
        except psycopg2.OperationalError as exc:
            print(f"Database connection error: {exc}")
            self._show_error("Unable to reach the database")
            return

        if valid:
            self.login_succeeded.emit(username)
        else:
            self._show_error("Invalid username or password")
            self.password_input.clear()

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()
