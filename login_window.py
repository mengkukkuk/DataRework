import psycopg2
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QFrame

import db
from i18n import tr
from i18n_widgets import QLabel, QPushButton, QCheckBox, QLineEdit, QWidget, LanguageToggle
from theme import THEMES, _render_stylesheet


class LoginWindow(QWidget):
    login_succeeded = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('Login'))
        self.setObjectName("loginWindow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(480, 640)
        self.resize(520, 690)
        theme = QSettings("DataRework", "ProductionRework").value("theme", "dark", type=str)
        self.setStyleSheet(_render_stylesheet(theme if theme in THEMES else "dark", "login.css"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(22)
        header = QHBoxLayout()
        brand = QLabel("DataRework")
        brand.setObjectName("loginBrand")
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(LanguageToggle(self))
        layout.addLayout(header)
        layout.addStretch()

        card = QFrame()
        card.setObjectName("loginCard")
        form = QVBoxLayout(card)
        form.setContentsMargins(30, 30, 30, 28)
        form.setSpacing(0)
        mark = QLabel("R")
        mark.setObjectName("loginMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(46, 46)
        form.addWidget(mark)
        form.addSpacing(20)
        title = QLabel(tr('Welcome back'))
        title.setObjectName("loginTitle")
        form.addWidget(title)
        form.addSpacing(6)
        subtitle = QLabel(tr('Sign in to Production Rework.'))
        subtitle.setObjectName("loginSubtitle")
        subtitle.setWordWrap(True)
        form.addWidget(subtitle)
        form.addSpacing(28)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(tr('Username'))
        self.username_input.setObjectName("loginUsername")
        self.username_input.setMinimumHeight(46)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(tr('Password'))
        self.password_input.setObjectName("loginPassword")
        self.password_input.setMinimumHeight(46)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        for label_text, field in (("Username", self.username_input), ("Password", self.password_input)):
            label = QLabel(tr(label_text))
            label.setObjectName("loginFieldLabel")
            label.setBuddy(field)
            form.addWidget(label)
            form.addSpacing(8)
            form.addWidget(field)
            form.addSpacing(18 if field is self.username_input else 12)

        self.show_password = QCheckBox(tr('Show password'))
        self.show_password.setObjectName("loginShowPassword")
        self.show_password.toggled.connect(
            lambda visible: self.password_input.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )
        )
        form.addWidget(self.show_password)
        form.addSpacing(24)
        self.login_button = QPushButton(tr('Login'))
        self.login_button.setObjectName("searchBtn")
        self.login_button.setMinimumHeight(46)
        self.login_button.setCursor(Qt.PointingHandCursor)
        form.addWidget(self.login_button)
        self.error_label = QLabel()
        self.error_label.setObjectName("loginError")
        self.error_label.setWordWrap(True)
        self.error_label.setTextFormat(Qt.PlainText)
        self.error_label.hide()
        form.addWidget(self.error_label)
        layout.addWidget(card)
        layout.addStretch()
        footer = QLabel(tr('Production Rework'))
        footer.setObjectName("loginFooter")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)
        self.setTabOrder(self.username_input, self.password_input)
        self.setTabOrder(self.password_input, self.show_password)
        self.setTabOrder(self.show_password, self.login_button)
        self.username_input.setFocus()

        self.login_button.clicked.connect(self._attempt_login)
        self.username_input.returnPressed.connect(self._attempt_login)
        self.password_input.returnPressed.connect(self._attempt_login)

    def _attempt_login(self):
        self.error_label.hide()
        username = self.username_input.text()
        password = self.password_input.text()

        try:
            result = db.authenticate(username, password)
        except psycopg2.OperationalError as exc:
            print(f"Database connection error: {exc}")
            self._show_error(tr('Unable to reach the database'))
            return

        if result is not None:
            permission, tag_name = result
            self.login_succeeded.emit(username, permission, tag_name)
        else:
            self._show_error(tr('Invalid username or password'))
            self.password_input.clear()

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()
