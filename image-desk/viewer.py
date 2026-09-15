"""Image Desk: a two-screen image viewer built with PySide6."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QGuiApplication, QImageReader, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.ico);;All files (*)"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico"}


def readable_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return ""


def format_mtime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


class ImageCanvas(QWidget):
    """Paint a static image inside a window without changing its aspect ratio."""

    def __init__(self, background: str = "#141924", parent: QWidget | None = None):
        super().__init__(parent)
        self.pixmap: QPixmap | None = None
        self.mode = "Fit"
        self.background = background
        self.setMinimumSize(160, 120)

    def set_image(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt method name
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background)
        if not self.pixmap or self.pixmap.isNull():
            return

        bounds = self.rect()
        size = self.pixmap.size()
        if self.mode == "Actual size":
            display_size = size
        else:
            aspect = Qt.AspectRatioMode.KeepAspectRatio
            if self.mode == "Fill":
                aspect = Qt.AspectRatioMode.KeepAspectRatioByExpanding
            display_size = size.scaled(bounds.size(), aspect)

        target = QRect(QPoint(0, 0), display_size)
        target.moveCenter(bounds.center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, self.pixmap)


class PresentationWindow(QWidget):
    def __init__(self, controller: "ViewerWindow"):
        super().__init__(None, Qt.WindowType.Window)
        self.controller = controller
        self.setWindowTitle("Image Desk | Presentation")
        self.canvas = ImageCanvas("#000000")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_PageDown):
            self.controller.step_image(1)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.controller.step_image(-1)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.controller.presentation_closed()
        super().closeEvent(event)


class ViewerWindow(QMainWindow):
    def __init__(self, initial_file: Path | None = None):
        super().__init__()
        self.setWindowTitle("Image Desk")
        self.setMinimumSize(820, 520)
        self.resize(1100, 700)

        self.current_path: Path | None = None
        self.image: QPixmap | None = None
        self.presentation: PresentationWindow | None = None
        self.presentation_screen = None

        self.make_interface()
        self.install_actions()
        self.refresh_screens()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self.refresh_screens)
        app.screenRemoved.connect(self.screen_removed)
        app.primaryScreenChanged.connect(self.refresh_screens)
        self.move_to_primary()
        if initial_file:
            self.load_image(initial_file)

    def make_interface(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QVBoxLayout(root)
        shell.setContentsMargins(18, 18, 18, 16)
        shell.setSpacing(14)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)
        title = QLabel("IMAGE DESK")
        title.setObjectName("brand")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.open_button = QPushButton("Open image…")
        self.open_button.clicked.connect(self.open_dialog)
        toolbar.addWidget(self.open_button)
        self.previous_button = QPushButton("◀ Previous")
        self.previous_button.clicked.connect(lambda: self.step_image(-1))
        toolbar.addWidget(self.previous_button)
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(lambda: self.step_image(1))
        toolbar.addWidget(self.next_button)
        shell.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        caption = QLabel("MAIN SCREEN PREVIEW")
        caption.setObjectName("section")
        preview_layout.addWidget(caption)
        self.preview = ImageCanvas()
        preview_layout.addWidget(self.preview, 1)
        self.placeholder = QLabel("Open an image to start")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        preview_layout.addWidget(self.placeholder)
        splitter.addWidget(preview_frame)

        details = QFrame()
        details.setObjectName("details")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(18, 18, 18, 18)
        details_layout.setSpacing(10)
        info_title = QLabel("FILE INFORMATION")
        info_title.setObjectName("section")
        details_layout.addWidget(info_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(12)
        info_layout.setContentsMargins(0, 4, 0, 4)
        self.info_values: dict[str, QLabel] = {}
        for heading in ("Name", "Folder", "Format", "Dimensions", "File size", "Last modified", "Color mode"):
            block = QWidget()
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(3)
            field = QLabel(heading.upper())
            field.setObjectName("field")
            value = QLabel("—")
            value.setObjectName("value")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            block_layout.addWidget(field)
            block_layout.addWidget(value)
            info_layout.addWidget(block)
            self.info_values[heading] = value
        info_layout.addStretch()
        scroll.setWidget(info_widget)
        details_layout.addWidget(scroll, 1)

        section = QLabel("PRESENTATION")
        section.setObjectName("section")
        details_layout.addWidget(section)
        details_layout.addWidget(QLabel("Display"))
        self.screen_combo = QComboBox()
        self.screen_combo.currentIndexChanged.connect(self.change_presentation_screen)
        details_layout.addWidget(self.screen_combo)
        details_layout.addWidget(QLabel("Image sizing"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Fit", "Fill", "Actual size"])
        self.mode_combo.currentTextChanged.connect(self.change_mode)
        details_layout.addWidget(self.mode_combo)
        self.fullscreen_button = QPushButton("Show fullscreen")
        self.fullscreen_button.setObjectName("primaryButton")
        self.fullscreen_button.clicked.connect(self.toggle_presentation)
        details_layout.addWidget(self.fullscreen_button)
        hint = QLabel("Esc closes fullscreen • ← / → changes image")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        details_layout.addWidget(hint)
        splitter.addWidget(details)
        splitter.setSizes([760, 340])
        shell.addWidget(splitter, 1)

        self.statusBar().showMessage("Ready. Open an image or drop one onto the window.")
        self.setAcceptDrops(True)
        self.update_controls()
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background: #10141d; color: #e8edf8; }
            QLabel#brand { font-size: 17px; font-weight: 800; letter-spacing: 2px; color: #f4f7ff; }
            QLabel#section { font-size: 11px; font-weight: 700; color: #8d9bb9; letter-spacing: 1px; }
            QLabel#field { color: #91a0bd; font-size: 10px; font-weight: 700; }
            QLabel#value { font-size: 13px; color: #eff3fd; }
            QLabel#hint { font-size: 11px; color: #94a1bc; }
            QLabel { color: #d6deef; }
            QFrame#previewFrame, QFrame#details { background: #1b2230; border-radius: 10px; }
            QScrollArea, QScrollArea QWidget { background: transparent; }
            QPushButton, QComboBox { background: #303b50; color: #f3f6ff; border: 1px solid #46536a;
                border-radius: 6px; padding: 8px 11px; min-height: 22px; }
            QPushButton:hover, QComboBox:hover { background: #40506a; }
            QPushButton:disabled { color: #8591a4; background: #252d3b; }
            QPushButton#primaryButton { background: #4769d3; border-color: #5777de; font-weight: 700; }
            QPushButton#primaryButton:hover { background: #5879e3; }
            QComboBox QAbstractItemView { background: #253047; color: #eff3fd; }
            QStatusBar { background: #10141d; color: #9ba8bd; }
        """)

    def install_actions(self) -> None:
        for text, shortcut, callback in (
            ("Open", QKeySequence.StandardKey.Open, self.open_dialog),
            ("Next image", Qt.Key.Key_Right, lambda: self.step_image(1)),
            ("Previous image", Qt.Key.Key_Left, lambda: self.step_image(-1)),
            ("Fullscreen", Qt.Key.Key_F11, self.toggle_presentation),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def move_to_primary(self) -> None:
        primary = QGuiApplication.primaryScreen()
        if not primary:
            return
        available = primary.availableGeometry()
        width = min(self.width(), available.width())
        height = min(self.height(), available.height())
        self.resize(width, height)
        self.move(available.x() + (available.width() - width) // 2,
                  available.y() + (available.height() - height) // 2)

    def refresh_screens(self, *_args) -> None:
        previously_selected = self.screen_combo.currentData()
        primary = QGuiApplication.primaryScreen()
        screens = QGuiApplication.screens()
        self.screen_combo.blockSignals(True)
        self.screen_combo.clear()
        for index, screen in enumerate(screens, start=1):
            suffix = " (main)" if screen is primary else " (secondary)"
            geom = screen.geometry()
            self.screen_combo.addItem(
                f"Display {index}: {screen.name() or 'Unnamed'} — {geom.width()}×{geom.height()}{suffix}", screen
            )
        selected = self.screen_combo.findData(previously_selected)
        if selected < 0:
            selected = next((i for i, s in enumerate(screens) if s is not primary), 0)
        if self.screen_combo.count():
            self.screen_combo.setCurrentIndex(selected)
        self.screen_combo.blockSignals(False)
        self.update_controls()

    def screen_removed(self, screen) -> None:
        if self.presentation and screen is self.presentation_screen:
            self.presentation.close()
            self.statusBar().showMessage("Presentation closed because the selected display disconnected.", 8000)
        self.refresh_screens()

    def change_presentation_screen(self, *_args) -> None:
        if not self.presentation:
            return
        screen = self.screen_combo.currentData()
        if screen is None or screen is self.presentation_screen:
            return
        self.presentation.showNormal()
        self.presentation.setGeometry(screen.geometry())
        if self.presentation.windowHandle():
            self.presentation.windowHandle().setScreen(screen)
        self.presentation_screen = screen
        self.presentation.showFullScreen()

    def open_dialog(self) -> None:
        start = str(self.current_path.parent) if self.current_path else str(Path.home())
        filename, _filter = QFileDialog.getOpenFileName(self, "Choose an image", start, IMAGE_FILTER)
        if filename:
            self.load_image(Path(filename))

    def load_image(self, path: Path, quiet: bool = False) -> bool:
        path = path.expanduser().resolve()
        if not path.is_file():
            if not quiet:
                QMessageBox.warning(self, "Cannot open file", f"File not found:\n{path}")
            return False

        reader = QImageReader(str(path))
        reader.setAutoTransform(True)  # Respect camera EXIF orientation on the main and fullscreen views.
        decoded = reader.read()
        if decoded.isNull():
            if not quiet:
                QMessageBox.warning(self, "Cannot open image", f"Could not decode this image:\n{path}\n\n{reader.errorString()}")
            return False

        pixmap = QPixmap.fromImage(decoded)
        if pixmap.isNull():
            if not quiet:
                QMessageBox.warning(self, "Cannot open image", f"Could not display this image:\n{path}")
            return False

        self.current_path = path
        self.image = pixmap
        self.preview.set_image(pixmap)
        self.placeholder.hide()
        if self.presentation:
            self.presentation.canvas.set_image(pixmap)

        stat = path.stat()
        file_format = bytes(reader.format()).decode("ascii", "replace").upper() or path.suffix[1:].upper()
        file_format = {"JPG": "JPEG", "TIF": "TIFF"}.get(file_format, file_format)
        values = {
            "Name": path.name,
            "Folder": str(path.parent),
            "Format": file_format,
            "Dimensions": f"{pixmap.width():,} × {pixmap.height():,} pixels",
            "File size": readable_size(stat.st_size),
            "Last modified": format_mtime(stat.st_mtime),
            "Color mode": "With transparency" if decoded.hasAlphaChannel() else "Opaque",
        }
        for label, value in values.items():
            self.info_values[label].setText(value)
        self.setWindowTitle(f"Image Desk — {path.name}")
        self.statusBar().showMessage(f"Showing {path.name}", 5000)
        self.update_controls()
        return True

    def sibling_images(self) -> list[Path]:
        if not self.current_path:
            return []
        try:
            return sorted((p for p in self.current_path.parent.iterdir()
                           if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
                          key=lambda p: p.name.casefold())
        except OSError:
            return []

    def step_image(self, direction: int) -> None:
        files = self.sibling_images()
        if not files or self.current_path not in files:
            return
        index = files.index(self.current_path)
        # Skip damaged images while keeping the current image visible if none load.
        for offset in range(1, len(files)):
            candidate = files[(index + direction * offset) % len(files)]
            if self.load_image(candidate, quiet=True):
                return

    def change_mode(self, mode: str) -> None:
        if self.presentation:
            self.presentation.canvas.set_mode(mode)

    def toggle_presentation(self) -> None:
        if self.presentation:
            self.presentation.close()
            return
        if not self.image:
            return
        screen = self.screen_combo.currentData()
        if screen is None or screen not in QGuiApplication.screens():
            self.refresh_screens()
            screen = self.screen_combo.currentData()
        if screen is None:
            QMessageBox.warning(self, "No display", "No display is available for presentation.")
            return
        self.presentation = PresentationWindow(self)
        self.presentation_screen = screen
        self.presentation.canvas.set_image(self.image)
        self.presentation.canvas.set_mode(self.mode_combo.currentText())
        # The initial geometry and explicit window screen both matter on systems
        # where showFullScreen() otherwise chooses the current primary display.
        self.presentation.setGeometry(screen.geometry())
        self.presentation.createWinId()
        if self.presentation.windowHandle():
            self.presentation.windowHandle().setScreen(screen)
        self.presentation.showFullScreen()
        self.presentation.activateWindow()
        self.presentation.setFocus()
        self.update_controls()

    def presentation_closed(self) -> None:
        self.presentation = None
        self.presentation_screen = None
        self.update_controls()

    def update_controls(self) -> None:
        has_image = self.image is not None
        self.previous_button.setEnabled(has_image)
        self.next_button.setEnabled(has_image)
        self.fullscreen_button.setEnabled(has_image and self.screen_combo.count() > 0)
        self.fullscreen_button.setText("Close fullscreen" if self.presentation else "Show fullscreen")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_image(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.presentation:
            self.presentation.close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Image Desk")
    initial = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    window = ViewerWindow(initial)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
