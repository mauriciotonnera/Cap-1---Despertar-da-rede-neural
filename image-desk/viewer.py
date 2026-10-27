"""Image Desk 3.0: media playlists and presentation control on two screens."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QGuiApplication, QImageReader, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

if __package__:
    from .playback import Playback, VIDEO_SUFFIXES, clock_text
    from .playlist import Playlist
    from .playlist_panel import PlaylistPanel
    from .session import read_session, write_session
else:
    from playback import Playback, VIDEO_SUFFIXES, clock_text
    from playlist import Playlist
    from playlist_panel import PlaylistPanel
    from session import read_session, write_session


IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.ico);;All files (*)"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico"}
MEDIA_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
MEDIA_FILTER = ("Images and video (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.ico *.mp4 *.mov *.m4v *.avi *.mkv *.webm);;"
                "Video (*.mp4 *.mov *.m4v *.avi *.mkv *.webm);;" + IMAGE_FILTER)


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
    """Paint a decoded frame, with optional presentation-only controls."""

    def __init__(self, background: str = "#141924", parent: QWidget | None = None):
        super().__init__(parent)
        self.pixmap: QPixmap | None = None
        self.mode = "Fit"
        self.background = background
        self.blackout = False
        self.countdown_text = ""
        self.setMinimumSize(160, 120)

    def set_image(self, pixmap: QPixmap | None) -> None:
        self.pixmap = pixmap
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def set_blackout(self, enabled):
        self.blackout = enabled
        self.update()

    def set_countdown(self, text):
        if self.countdown_text != text:
            self.countdown_text = text
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt method name
        painter = QPainter(self)
        if self.blackout:
            painter.fillRect(self.rect(), "#000000")
            return
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
        if self.countdown_text:
            font = painter.font()
            font.setPixelSize(max(18, min(48, self.height() // 22)))
            font.setBold(True)
            painter.setFont(font)
            text_width = painter.fontMetrics().horizontalAdvance(self.countdown_text)
            text_height = painter.fontMetrics().height()
            badge = QRect(self.width() - text_width - 48, self.height() - text_height - 40,
                          text_width + 24, text_height + 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 190))
            painter.drawRoundedRect(badge, 6, 6)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, self.countdown_text)


class PresentationWindow(QWidget):
    def __init__(self, controller: "ViewerWindow"):
        super().__init__(None, Qt.WindowType.Window)
        self.controller = controller
        self.setWindowTitle("Image Desk | Presentation")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.canvas = ImageCanvas("#000000")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Space:
            self.controller.space_pressed()
        elif key == Qt.Key.Key_B:
            self.controller.blackout_button.toggle()
        elif key == Qt.Key.Key_F11:
            self.close()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
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
        self.setMinimumSize(940, 680)
        self.resize(1180, 850)

        self.current_path: Path | None = None
        self.image: QPixmap | None = None
        self.presentation: PresentationWindow | None = None
        self.presentation_screen = None
        self.playback = Playback(self)
        self.playlist = Playlist(self.playback, lambda path: self.load_image(
            path, quiet=True, from_playlist=True), self)
        self.session_path = None
        self.blackout = False
        self._seeking = False

        self.make_interface()
        self.playback.frameReady.connect(self.show_frame)
        self.playback.changed.connect(self.update_playback_controls)
        self.playback.metadataChanged.connect(self.set_info)
        self.playback.failed.connect(self.playback_error)
        self.playlist.changed.connect(self.update_playback_controls)
        self.playlist.notice.connect(lambda message: self.statusBar().showMessage(message, 10000))
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(100)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start()
        self.install_actions()
        self.refresh_screens()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self.refresh_screens)
        app.screenRemoved.connect(self.screen_removed)
        app.primaryScreenChanged.connect(self.refresh_screens)
        self.move_to_primary()
        if initial_file:
            if str(initial_file).lower().endswith(".imagedesk.json"):
                self.open_session_file(initial_file)
            else:
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

        self.open_button = QPushButton("Open media…")
        self.open_button.clicked.connect(self.open_dialog)
        toolbar.addWidget(self.open_button)
        self.previous_button = QPushButton("◀ Previous")
        self.previous_button.clicked.connect(lambda: self.step_image(-1))
        toolbar.addWidget(self.previous_button)
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(lambda: self.step_image(1))
        toolbar.addWidget(self.next_button)
        self.playlist_button = QPushButton("Playlist")
        self.playlist_button.setCheckable(True)
        self.playlist_button.setChecked(True)
        toolbar.addWidget(self.playlist_button)
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
        self.placeholder = QLabel("Open an image or video to start")
        self.placeholder.setWordWrap(True)
        self.placeholder.setTextFormat(Qt.TextFormat.PlainText)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        preview_layout.addWidget(self.placeholder)
        self.transport = QWidget()
        transport_layout = QVBoxLayout(self.transport)
        transport_layout.setContentsMargins(0, 8, 0, 0)
        buttons = QHBoxLayout()
        self.play_button = QPushButton("Pause")
        self.play_button.clicked.connect(self.space_pressed)
        self.restart_button = QPushButton("Restart")
        self.restart_button.clicked.connect(self.restart_current)
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItems(["Play once", "Loop"])
        self.repeat_combo.setToolTip("Play once holds the last frame. Loop repeats the current file.")
        self.repeat_combo.currentIndexChanged.connect(lambda index: self.playback.set_loop(index == 1))
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.restart_button)
        buttons.addStretch()
        buttons.addWidget(self.repeat_combo)
        transport_layout.addLayout(buttons)
        timeline = QHBoxLayout()
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setTracking(False)
        self.seek_slider.sliderPressed.connect(self.seek_started)
        self.seek_slider.sliderReleased.connect(self.seek_finished)
        self.seek_slider.valueChanged.connect(self.seek_value_changed)
        self.time_label = QLabel("00:00 / 00:00")
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.time_label)
        transport_layout.addLayout(timeline)
        audio_row = QHBoxLayout()
        self.playback_label = QLabel("Ready")
        audio_row.addWidget(self.playback_label)
        audio_row.addStretch()
        self.volume_label = QLabel("Volume")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(lambda v: self.playback.audio.setVolume(v / 100))
        self.mute_button = QPushButton("Mute")
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(self.change_mute)
        audio_row.addWidget(self.volume_label)
        audio_row.addWidget(self.volume_slider)
        audio_row.addWidget(self.mute_button)
        transport_layout.addLayout(audio_row)
        preview_layout.addWidget(self.transport)
        self.transport.hide()
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setChildrenCollapsible(False)
        self.left_splitter.addWidget(preview_frame)
        self.playlist_panel = PlaylistPanel(self.playlist)
        self.playlist_panel.addRequested.connect(self.add_playlist_dialog)
        self.playlist_panel.openRequested.connect(self.open_session_dialog)
        self.playlist_panel.saveRequested.connect(self.save_session_dialog)
        self.playlist_button.toggled.connect(self.playlist_panel.setVisible)
        self.left_splitter.addWidget(self.playlist_panel)
        self.left_splitter.setSizes([510, 250])
        splitter.addWidget(self.left_splitter)

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
        for heading in ("Name", "Folder", "Format", "Dimensions", "File size", "Last modified", "Color mode", "Duration", "Frame rate", "Frames", "Codec"):
            block = QWidget()
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(3)
            field = QLabel(heading.upper())
            field.setObjectName("field")
            value = QLabel("—")
            value.setObjectName("value")
            value.setTextFormat(Qt.TextFormat.PlainText)
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
        details_layout.addWidget(QLabel("Media sizing"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Fit", "Fill", "Actual size"])
        self.mode_combo.currentTextChanged.connect(self.change_mode)
        details_layout.addWidget(self.mode_combo)
        self.fullscreen_button = QPushButton("Show fullscreen")
        self.fullscreen_button.setObjectName("primaryButton")
        self.fullscreen_button.clicked.connect(self.toggle_presentation)
        details_layout.addWidget(self.fullscreen_button)
        self.blackout_button = QPushButton("Blackout (B)")
        self.blackout_button.setObjectName("blackoutButton")
        self.blackout_button.setCheckable(True)
        self.blackout_button.setToolTip("Black out the fullscreen display. Playback and audio continue; the main preview stays visible.")
        self.blackout_button.toggled.connect(self.set_blackout)
        details_layout.addWidget(self.blackout_button)
        self.output_status = QLabel("OUTPUT CLOSED")
        self.output_status.setObjectName("section")
        details_layout.addWidget(self.output_status)
        self.remaining_label = QLabel("—")
        self.remaining_label.setObjectName("countdown")
        details_layout.addWidget(self.remaining_label)
        remaining_hint = QLabel("Remaining in current item")
        remaining_hint.setObjectName("hint")
        details_layout.addWidget(remaining_hint)
        self.output_timer_check = QCheckBox("Show countdown on fullscreen")
        self.output_timer_check.toggled.connect(self.update_countdown)
        details_layout.addWidget(self.output_timer_check)
        hint = QLabel("Esc closes fullscreen · B toggles blackout\nSpace pauses · ← / → changes item")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        details_layout.addWidget(hint)
        splitter.addWidget(details)
        splitter.setSizes([760, 340])
        shell.addWidget(splitter, 1)

        self.statusBar().showMessage("Ready. Open an image, GIF or video, or drop a file onto the window.")
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
            QFrame#previewFrame, QFrame#details, QFrame#playlistFrame { background: #1b2230; border-radius: 10px; }
            QScrollArea, QScrollArea QWidget { background: transparent; }
            QPushButton, QComboBox { background: #303b50; color: #f3f6ff; border: 1px solid #46536a;
                border-radius: 6px; padding: 8px 11px; min-height: 22px; }
            QPushButton:hover, QComboBox:hover { background: #40506a; }
            QPushButton:disabled { color: #8591a4; background: #252d3b; }
            QPushButton#primaryButton { background: #4769d3; border-color: #5777de; font-weight: 700; }
            QPushButton#primaryButton:hover { background: #5879e3; }
            QPushButton:checked { background: #3c5290; border-color: #7290e9; }
            QPushButton#blackoutButton:checked { background: #932f44; border-color: #da6b80; }
            QLabel#countdown { font-size: 29px; font-weight: 700; color: #f4f7ff; }
            QCheckBox { color: #d6deef; spacing: 6px; }
            QListWidget, QDoubleSpinBox { color: #eff3fd; background: #141924; border: 1px solid #364258; border-radius: 5px; }
            QListWidget::item { padding: 5px; }
            QListWidget::item:selected { background: #3c5290; }
            QFrame#playlistFrame QPushButton { padding: 4px 8px; min-height: 18px; }
            QDoubleSpinBox { padding: 5px; }
            QComboBox QAbstractItemView { background: #253047; color: #eff3fd; }
            QSlider::groove:horizontal { height: 5px; background: #364258; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #6586ee; border-radius: 2px; }
            QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #dce6ff; border-radius: 6px; }
            QStatusBar { background: #10141d; color: #9ba8bd; }
        """)

    def install_actions(self) -> None:
        for text, shortcut, callback in (
            ("Open", QKeySequence.StandardKey.Open, self.open_dialog),
            ("Next item", Qt.Key.Key_Right, lambda: self.step_image(1)),
            ("Previous item", Qt.Key.Key_Left, lambda: self.step_image(-1)),
            ("Fullscreen", Qt.Key.Key_F11, self.toggle_presentation),
            ("Play / pause", Qt.Key.Key_Space, self.space_pressed),
            ("Blackout", Qt.Key.Key_B, self.blackout_button.toggle),
            ("Save session", QKeySequence.StandardKey.Save, self.save_session_dialog),
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
        filename, _filter = QFileDialog.getOpenFileName(self, "Choose an image or video", start, MEDIA_FILTER)
        if filename:
            self.load_image(Path(filename))

    def add_playlist_dialog(self):
        start = str(self.current_path.parent) if self.current_path else str(Path.home())
        names, _ = QFileDialog.getOpenFileNames(self, "Add media to playlist", start, MEDIA_FILTER)
        if names:
            self.add_playlist_files([Path(name) for name in names])

    def add_playlist_files(self, paths):
        if self.playlist.active:
            self.statusBar().showMessage("Stop the playlist before adding or rearranging items.", 6000)
            return
        accepted = [Path(path) for path in paths if Path(path).suffix.lower() in MEDIA_SUFFIXES]
        self.playlist.add(accepted)
        self.playlist_button.setChecked(True)
        self.statusBar().showMessage(f"Added {len(accepted)} item(s) to the playlist.", 5000)

    def session_settings(self):
        return {"still_seconds": self.playlist.still_seconds,
                "repeat_playlist": self.playlist.repeat,
                "clip_loop": self.playlist._saved_loop if self.playlist.active else self.playback.loop,
                "sizing": self.mode_combo.currentText(),
                "show_countdown": self.output_timer_check.isChecked(),
                "volume": self.volume_slider.value(), "muted": self.mute_button.isChecked()}

    def save_session_file(self, path):
        paths = self.playlist.paths or ([self.current_path] if self.current_path else [])
        write_session(path, paths, self.session_settings())
        self.session_path = Path(path).resolve()
        self.statusBar().showMessage(f"Session saved: {self.session_path.name}", 6000)

    def save_session_dialog(self):
        suggested = self.session_path or Path.home() / "My-show.imagedesk.json"
        name, _ = QFileDialog.getSaveFileName(self, "Save Image Desk session", str(suggested),
                                             "Image Desk session (*.imagedesk.json)")
        if not name:
            return
        if not name.lower().endswith(".imagedesk.json"):
            name += ".imagedesk.json"
        try:
            self.save_session_file(Path(name))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot save session", str(error))

    def open_session_dialog(self):
        start = self.session_path.parent if self.session_path else Path.home()
        name, _ = QFileDialog.getOpenFileName(self, "Open Image Desk session", str(start),
                                             "Image Desk session (*.imagedesk.json);;JSON files (*.json)")
        if name:
            self.open_session_file(Path(name))

    def open_session_file(self, path, quiet=False):
        try:
            paths, settings = read_session(path)
            if any(p.suffix.lower() not in MEDIA_SUFFIXES for p in paths):
                raise ValueError("The session contains an unsupported media file type.")
        except (OSError, ValueError) as error:
            if not quiet:
                QMessageBox.warning(self, "Cannot open session", str(error))
            return False
        self.playlist.stop()
        self.playback.clear()
        self.current_path = self.image = None
        self.preview.set_image(None)
        if self.presentation:
            self.presentation.canvas.set_image(None)
        self.set_info({key: "—" for key in self.info_values})
        self.playlist.set_items(paths)
        self.playlist_panel.seconds.setValue(settings["still_seconds"])
        self.playlist_panel.repeat.setChecked(settings["repeat_playlist"])
        self.repeat_combo.setCurrentIndex(int(settings["clip_loop"]))
        self.playback.set_loop(settings["clip_loop"])
        self.mode_combo.setCurrentText(settings["sizing"])
        self.output_timer_check.setChecked(settings["show_countdown"])
        self.volume_slider.setValue(settings["volume"])
        self.mute_button.setChecked(settings["muted"])
        self.session_path = Path(path).resolve()
        self.playlist_button.setChecked(True)
        self.placeholder.setText("Session loaded. Start the playlist when ready.")
        self.placeholder.show()
        self.setWindowTitle(f"Image Desk — {self.session_path.name}")
        missing = sum(not p.is_file() for p in paths)
        self.statusBar().showMessage(f"Loaded {len(paths)} item(s). {missing} missing file(s).", 10000)
        self.update_controls()
        self.update_countdown()
        return True

    def load_image(self, path: Path, quiet: bool = False, from_playlist=False) -> bool:
        if not from_playlist:
            if self.playlist.active:
                self.playlist.stop(pause=False)
            self.playlist.index = -1
            self.playlist.changed.emit()
        self._seeking = False
        path = path.expanduser().resolve()
        if not path.is_file():
            if not quiet:
                QMessageBox.warning(self, "Cannot open file", f"File not found:\n{path}")
            return False

        if path.suffix.lower() in VIDEO_SUFFIXES or path.suffix.lower() == ".gif":
            try:
                stat = path.stat()
                self.current_path = path
                self.image = None
                self.preview.set_image(None)
                if self.presentation:
                    self.presentation.canvas.set_image(None)
                self.set_info({key: "—" for key in self.info_values})
                self.set_info({"Name": path.name, "Folder": str(path.parent),
                               "Format": path.suffix[1:].upper(), "File size": readable_size(stat.st_size),
                               "Last modified": format_mtime(stat.st_mtime)})
                self.placeholder.setText("Loading media…")
                self.placeholder.show()
                if path.suffix.lower() == ".gif":
                    self.playback.load_gif(path)
                else:
                    self.playback.load_video(path)
                self.setWindowTitle(f"Image Desk — {path.name}")
                self.statusBar().showMessage(f"Opened {path.name}", 5000)
                self.update_controls()
                return True
            except (OSError, ValueError) as error:
                self.playback.clear()
                self.playback_error(str(error))
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

        try:
            stat = path.stat()
        except OSError as error:
            if not quiet:
                QMessageBox.warning(self, "Cannot open file", str(error))
            return False
        self.playback.clear()
        self.current_path = path
        self.show_frame(decoded)
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
            "Duration": "—", "Frame rate": "—", "Frames": "—", "Codec": "—",
        }
        self.set_info(values)
        self.setWindowTitle(f"Image Desk — {path.name}")
        self.statusBar().showMessage(f"Showing {path.name}", 5000)
        self.update_controls()
        return True

    def show_frame(self, frame):
        self.image = QPixmap.fromImage(frame)
        self.preview.set_image(self.image)
        if self.presentation:
            self.presentation.canvas.set_image(self.image)
        self.placeholder.hide()

    def set_info(self, values):
        for label, value in values.items():
            if label in self.info_values:
                self.info_values[label].setText(value)

    def playback_error(self, text):
        self.placeholder.setText(f"Cannot play this file: {text}")
        self.placeholder.show()
        self.statusBar().showMessage(f"Playback error: {text}")
        self.update_controls()

    def space_pressed(self):
        if self.playlist.active:
            if self.playlist.paused:
                self.playlist.resume()
            else:
                self.playlist.pause()
        elif self.playback.kind in ("video", "gif"):
            self.playback.toggle()
        else:
            self.step_image(1)

    def restart_current(self):
        if self.playlist.active:
            self.playlist.restart_item()
        else:
            self.playback.restart()

    def set_blackout(self, enabled):
        self.blackout = enabled
        self.blackout_button.setText("Restore output (B)" if enabled else "Blackout (B)")
        if self.presentation:
            self.presentation.canvas.set_blackout(enabled)
        self.update_controls()

    def remaining_milliseconds(self):
        p, c = self.playback, self.playlist
        if not self.current_path or p.error:
            return None
        if p.kind == "video" and p.duration > 0:
            return max(0, p.duration - p.position) if not p.ended else 0
        if c.index >= 0 and c.paths[c.index] == self.current_path and c.timed_still:
            return c.still_remaining
        return None

    def update_countdown(self, *_args):
        remaining = self.remaining_milliseconds()
        if remaining is not None:
            text = clock_text(remaining + 999)  # Round up while any time remains.
        elif self.current_path and self.playback.kind == "gif" and not self.playback.error:
            p = self.playback
            count = 0 if p.ended else max(0, p.frame_count - p.position)
            text = f"{count} frame{'s' if count != 1 else ''}"
        elif self.current_path and self.playback.kind == "image":
            text = "Held"
        else:
            text = "—"
        self.remaining_label.setText(text)
        if self.presentation:
            self.presentation.canvas.set_countdown(
                f"{text} remaining" if self.output_timer_check.isChecked() and text not in ("—", "Held") else "")

    def change_mute(self, muted):
        self.playback.audio.setMuted(muted)
        self.mute_button.setText("Unmute" if muted else "Mute")

    def seek_started(self):
        self._seeking = True

    def seek_finished(self):
        self._seeking = False
        self.playlist.cancel_transition()
        self.playback.seek(self.seek_slider.value())

    def seek_value_changed(self, value):
        if not self._seeking:
            self.playlist.cancel_transition()
            self.playback.seek(value)

    def update_playback_controls(self):
        p = self.playback
        self.transport.setVisible(p.kind in ("video", "gif"))
        self.play_button.setText("Pause" if p.playing else "Play")
        self.play_button.setEnabled(not p.error)
        self.restart_button.setEnabled(not p.error)
        self.seek_slider.setEnabled(p.seekable and not p.error)
        self.playback_label.setText("Cannot play" if p.error else "Finished" if p.ended else "Playing" if p.playing else "Paused")
        self.repeat_combo.setEnabled(not self.playlist.active)
        self.repeat_combo.blockSignals(True)
        self.repeat_combo.setCurrentIndex(0 if self.playlist.active else int(p.loop))
        self.repeat_combo.blockSignals(False)
        self.repeat_combo.setToolTip("Playlist items play once. Use Repeat playlist for the sequence." if self.playlist.active
                                    else "Play once holds the last frame. Loop repeats the current file.")
        self.seek_slider.blockSignals(True)
        if p.kind == "gif":
            self.seek_slider.setRange(0, max(0, p.frame_count - 1))
            self.time_label.setText(f"Frame {p.position + 1} / {p.frame_count}")
        else:
            self.seek_slider.setRange(0, min(p.duration, 2147483647))
            self.time_label.setText(f"{clock_text(p.position)} / {clock_text(p.duration)}")
        if not self._seeking:
            self.seek_slider.setValue(p.position)
        self.seek_slider.blockSignals(False)
        for widget in (self.volume_label, self.volume_slider, self.mute_button):
            widget.setVisible(p.kind == "video")
        self.update_countdown()

    def sibling_images(self) -> list[Path]:
        if not self.current_path:
            return []
        try:
            return sorted((p for p in self.current_path.parent.iterdir()
                           if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES),
                          key=lambda p: p.name.casefold())
        except OSError:
            return []

    def step_image(self, direction: int) -> None:
        if self.playlist.active:
            self.playlist.step(direction)
            return
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
        if not self.current_path:
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
        self.presentation.canvas.set_blackout(self.blackout)
        self.update_countdown()
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
        has_image = self.current_path is not None
        self.previous_button.setEnabled(has_image)
        self.next_button.setEnabled(has_image)
        self.fullscreen_button.setEnabled(has_image and self.screen_combo.count() > 0)
        self.fullscreen_button.setText("Close fullscreen" if self.presentation else "Show fullscreen")
        state = ("OUTPUT BLACKED OUT" if self.presentation else "BLACKOUT ARMED") if self.blackout else (
            "OUTPUT LIVE" if self.presentation else "OUTPUT CLOSED")
        self.output_status.setText(state)
        self.output_status.setStyleSheet("color: #ff9cab;" if self.blackout else "color: #8d9bb9;")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if len(paths) > 1:
            self.add_playlist_files(paths)
        elif paths:
            if str(paths[0]).lower().endswith(".imagedesk.json"):
                self.open_session_file(paths[0])
            else:
                self.load_image(paths[0])
        if paths:
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.countdown_timer.stop()
        self.playlist.stop()
        self.playback.clear()
        if self.presentation:
            self.presentation.close()
        super().closeEvent(event)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from smoke_test import run
        return run(ViewerWindow, sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName("Image Desk")
    app.setApplicationVersion("3.0")
    initial = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    window = ViewerWindow(initial)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
