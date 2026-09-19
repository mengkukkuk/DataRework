"""Non-modal product image preview, independent of the card's lifetime."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout

from i18n import tr
from i18n_widgets import QDialog, QLabel, QPushButton


class AvatarLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ImagePreview(QDialog):
    def __init__(self, path, product_name, parent=None):
        super().__init__(parent)
        self.image_path = path
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(tr('Image preview — {p0}', p0=product_name))
        self.setMinimumSize(300, 300)
        available = self.screen().availableGeometry()
        self.resize(min(620, available.width()), min(720, available.height()))
        layout = QVBoxLayout(self)
        title = QLabel(product_name)
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title.setObjectName('dialogTitle')
        layout.addWidget(title)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setAccessibleName(product_name)
        layout.addWidget(self.image, 1)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        self.original = QPixmap.fromImage(reader.read())
        if self.original.isNull():
            self.image.setText(tr('Unable to open image.'))
        close = QPushButton(tr('Close'))
        close.setObjectName('ghostBtn')
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignRight)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'original') and not self.original.isNull():
            self.image.setPixmap(self.original.scaled(
                self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
