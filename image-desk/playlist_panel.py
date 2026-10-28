"""Compact playlist controls in Image Desk's existing dark interface."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QVBoxLayout)


class PlaylistPanel(QFrame):
    addRequested = Signal()
    openRequested = Signal()
    saveRequested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("playlistFrame")
        self._last_index = -2
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        header = QHBoxLayout()
        caption = QLabel("PLAYLISTS")
        caption.setObjectName("section")
        header.addWidget(caption)
        header.addStretch()
        self.add_button = QPushButton("Add files…")
        self.add_button.clicked.connect(self.addRequested.emit)
        self.open_button = QPushButton("Open session…")
        self.open_button.clicked.connect(self.openRequested.emit)
        save = QPushButton("Save session…")
        save.setToolTip("Save every named playlist and the presentation settings")
        save.clicked.connect(self.saveRequested.emit)
        for button in (self.add_button, self.open_button, save):
            header.addWidget(button)
        layout.addLayout(header)
        names = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.setMinimumWidth(120)
        self.selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMinimumContentsLength(10)
        self.selector.setToolTip("Select a playlist. Stop playback before switching playlists.")
        self.selector.currentIndexChanged.connect(self.select_playlist)
        self.new_button = QPushButton("+ Add playlist")
        self.new_button.clicked.connect(self.new_playlist)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self.rename_playlist)
        names.addWidget(self.selector, 1)
        names.addWidget(self.new_button)
        names.addWidget(self.rename_button)
        layout.addLayout(names)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumHeight(55)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setToolTip("Double-click an item to start the playlist from there. Add files or drop multiple files onto the main window.")
        self.list.itemDoubleClicked.connect(lambda item: controller.start(self.list.row(item)))
        self.list.itemSelectionChanged.connect(self.update_buttons)
        body.addWidget(self.list, 1)
        edits = QVBoxLayout()
        self.up = QPushButton("↑")
        self.up.setToolTip("Move selected item up")
        self.down = QPushButton("↓")
        self.down.setToolTip("Move selected item down")
        self.remove = QPushButton("Remove")
        self.up.clicked.connect(lambda: self.move(-1))
        self.down.clicked.connect(lambda: self.move(1))
        self.remove.clicked.connect(lambda: controller.remove(self.selected_rows()))
        for button in (self.up, self.down, self.remove):
            edits.addWidget(button)
        body.addLayout(edits)
        layout.addLayout(body, 1)
        controls = QHBoxLayout()
        self.start = QPushButton("Start playlist")
        self.start.clicked.connect(self.toggle)
        self.stop = QPushButton("Stop")
        self.stop.clicked.connect(lambda: controller.stop())
        self.repeat = QCheckBox("Repeat playlist")
        self.repeat.toggled.connect(self.change_repeat)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.5, 3600)
        self.seconds.setDecimals(1)
        self.seconds.setSingleStep(0.5)
        self.seconds.setValue(5)
        self.seconds.setSuffix(" s")
        self.seconds.setToolTip("Display time for each still image, including single-frame GIFs")
        self.seconds.valueChanged.connect(lambda value: setattr(controller, "still_seconds", value))
        controls.addWidget(self.start)
        controls.addWidget(self.stop)
        controls.addWidget(self.repeat)
        controls.addStretch()
        controls.addWidget(QLabel("Stills"))
        controls.addWidget(self.seconds)
        layout.addLayout(controls)
        self.status = QLabel("Add files, then start the playlist.")
        self.status.setObjectName("hint")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(0)
        layout.addWidget(self.status)
        controller.itemsChanged.connect(self.refresh_items)
        controller.playlistsChanged.connect(self.refresh_playlists)
        controller.changed.connect(self.refresh_state)
        self.refresh_playlists()
        self.refresh_items()

    def refresh_playlists(self):
        c = self.controller
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItems([entry.name for entry in c.playlists])
        self.selector.setCurrentIndex(c.selected_playlist)
        self.selector.blockSignals(False)
        self.repeat.blockSignals(True)
        self.repeat.setChecked(c.repeat)
        self.repeat.blockSignals(False)
        self.seconds.blockSignals(True)
        self.seconds.setValue(c.still_seconds)
        self.seconds.blockSignals(False)

    def select_playlist(self, index):
        if not self.controller.select_playlist(index):
            self.refresh_playlists()

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "Add playlist", "Playlist name:",
                                        text=self.controller.suggested_name())
        if ok:
            try:
                self.controller.add_playlist(name)
            except ValueError as error:
                QMessageBox.warning(self, "Cannot add playlist", str(error))

    def rename_playlist(self):
        name, ok = QInputDialog.getText(self, "Rename playlist", "Playlist name:",
                                        text=self.controller.current_playlist.name)
        if ok:
            try:
                self.controller.rename_playlist(name)
            except ValueError as error:
                QMessageBox.warning(self, "Cannot rename playlist", str(error))

    def selected_rows(self):
        return sorted(self.list.row(item) for item in self.list.selectedItems())

    def change_repeat(self, value):
        self.controller.repeat = value
        self.refresh_state()

    def move(self, direction):
        rows = self.selected_rows()
        if len(rows) == 1:
            row = self.controller.move(rows[0], direction)
            self.list.setCurrentRow(row)

    def toggle(self):
        c = self.controller
        if not c.active:
            c.start(max(0, self.list.currentRow()))
        elif c.paused:
            c.resume()
        else:
            c.pause()

    def refresh_items(self):
        self.list.clear()
        for i, path in enumerate(self.controller.paths):
            suffix = " — missing" if not path.is_file() else ""
            item = QListWidgetItem(f"{i + 1:02}  {path.name}{suffix}")
            item.setToolTip(str(path))
            self.list.addItem(item)
        self._last_index = -2
        self.refresh_state()

    def refresh_state(self):
        c = self.controller
        self.start.setText("Resume" if c.active and c.paused else "Pause playlist" if c.active else "Start playlist")
        self.start.setEnabled(bool(c.paths))
        self.stop.setEnabled(c.active)
        if c.index != self._last_index:
            self._last_index = c.index
            if c.index >= 0:
                self.list.setCurrentRow(c.index)
                self.list.scrollToItem(self.list.item(c.index))
        if c.index >= 0:
            next_index = c.index + 1
            if next_index >= len(c.paths) and c.repeat:
                next_index = 0
            next_name = c.paths[next_index].name if next_index < len(c.paths) else "End of playlist"
            self.status.setText(f"{c.status} · Item {c.index + 1} of {len(c.paths)} · Next: {next_name}")
        else:
            self.status.setText(f"{len(c.paths)} item(s) · Double-click a file or start the playlist.")
        self.update_buttons()

    def update_buttons(self):
        c = self.controller
        rows = self.selected_rows()
        self.add_button.setEnabled(not c.active)
        self.open_button.setEnabled(not c.active)
        self.selector.setEnabled(not c.active)
        self.new_button.setEnabled(not c.active)
        self.new_button.setToolTip("Stop playback before adding a playlist." if c.active else "Create and name another playlist")
        self.remove.setEnabled(not c.active and bool(rows))
        self.up.setEnabled(not c.active and len(rows) == 1 and rows[0] > 0)
        self.down.setEnabled(not c.active and len(rows) == 1 and rows[0] < len(c.paths) - 1)
