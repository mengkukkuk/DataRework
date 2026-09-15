import sys

from PySide6.QtWidgets import QApplication

from login_window import LoginWindow
from main_window import MainWindow

class App:
    def __init__(self):
        self.login_window = LoginWindow()
        self.main_window = None
        self.login_window.login_succeeded.connect(self._on_login_succeeded)
        self.login_window.show()

    def _on_login_succeeded(self, username, permission):
        self.main_window = MainWindow(username, permission)
        self.main_window.show()
        self.login_window.close()


def main():
    app = QApplication(sys.argv)
    controller = App()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
