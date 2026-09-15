from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self, username):
        super().__init__()
        self.setWindowTitle("Main App")
        self.resize(1300, 700)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel(f"Welcome, {username}"))
        self.setCentralWidget(central)
