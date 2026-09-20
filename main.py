import ctypes
import logging
import os
import sys

from dotenv import load_dotenv
# Resolved against __file__ rather than cwd, so it finds the source-tree .env
# when running from source and the bundled one inside _MEIPASS when frozen.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from login_window import LoginWindow
from main_window import MainWindow
import service_manager
from typography import ui_font

DEV_MODE = os.environ.get("DEV_MODE", "false").strip().lower() in ("1", "true", "yes")

# Resolved next to this file, which under PyInstaller is the _MEIPASS extraction
# dir -- so the .ico must be listed in DataRework.spec's datas (same arrangement
# as style.css in main_window.py).
APP_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.ico")


class App:
    def __init__(self):
        self.login_window = None
        self.main_window = None

        if DEV_MODE:
            # Skip the login screen entirely and open straight into Production
            # Rework as an admin, for local UI development.
            self._on_login_succeeded("admin", "admin","vm000")
        else:
            self.login_window = LoginWindow()
            self.login_window.login_succeeded.connect(self._on_login_succeeded)
            self.login_window.show()

    def _on_login_succeeded(self, username, permission, tag_name):
        self.main_window = MainWindow(username, permission,tag_name)
        self.main_window.show()
        if self.login_window:
            self.login_window.close()


def main():
    # Elevated re-launch of ourselves (see service_manager._elevate_and_install):
    # do the NSSM install and exit without starting the GUI.
    if "--install-service" in sys.argv:
        logging.basicConfig(level=logging.INFO)
        service_manager.install_service()
        return

    # Without an explicit AppUserModelID, Windows groups our windows under the
    # host process (python.exe when running from source) and shows *its* icon in
    # the taskbar instead of ours.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DataRework")

    app = QApplication(sys.argv)
    app.setFont(ui_font())
    # Applies to every top-level window (login + main), for both the title bar
    # and the taskbar button.
    app.setWindowIcon(QIcon(APP_ICON_PATH))
    controller = App()
    # Register/start the sync service once the window is already up, so the
    # NSSM install (and its UAC prompt) never delays the GUI appearing.
    QTimer.singleShot(0, service_manager.ensure_service_running)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
