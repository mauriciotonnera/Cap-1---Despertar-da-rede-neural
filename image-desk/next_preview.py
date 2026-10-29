"""Small, silent next-cue previews with bounded caching and stale-frame guards."""

from collections import OrderedDict
from pathlib import Path

from qtpy import PYSIDE2
from qtpy.QtCore import QObject, QRunnable, QSize, QThreadPool, QTimer, QUrl, Qt, Signal
from qtpy.QtGui import QImage, QImageReader, QPixmap, QTransform
from qtpy.QtWidgets import QFrame, QLabel, QVBoxLayout

from media_info import MediaCatalog, VIDEO


class _Signals(QObject):
    ready = Signal(object, QImage)


class _ImageJob(QRunnable):
    def __init__(self, key):
        super().__init__()
        self.key = key
        self.signals = _Signals()

    def run(self):
        reader = QImageReader(self.key[0])
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            reader.setScaledSize(size.scaled(QSize(288, 162), Qt.AspectRatioMode.KeepAspectRatio))
        self.signals.ready.emit(self.key, reader.read())


class NextPreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(164)
        self.setObjectName("nextPreview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        self.heading = QLabel("UP NEXT")
        self.heading.setObjectName("section")
        layout.addWidget(self.heading)
        self.picture = QLabel("No next item")
        self.picture.setFixedSize(148, 84)
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setStyleSheet("background: #0d1119; color: #94a1bc; border-radius: 4px;")
        layout.addWidget(self.picture)
        self.name = QLabel("Add media to a playlist")
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setWordWrap(True)
        self.name.setMaximumHeight(55)
        layout.addWidget(self.name)
        self.detail = QLabel("")
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setWordWrap(True)
        self.detail.setObjectName("hint")
        layout.addWidget(self.detail)
        layout.addStretch()
        self.path = None
        self.thumbnail = QImage()
        self.key = None
        self.decoder = self.job = None
        self.closed = False
        self.cache = OrderedDict()
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(100)
        self.debounce.timeout.connect(self._load)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(5000)
        self.timeout.timeout.connect(self._failed)

    def set_item(self, path, detail="", empty="No next item"):
        if self.closed:
            return
        path = Path(path) if path else None
        key = (str(path), MediaCatalog.stamp(path)) if path else None
        self.detail.setText(detail)
        self.name.setText(path.name if path else empty)
        self.name.setToolTip(str(path) if path else "")
        if key == self.key:
            return
        self._release()
        self.debounce.stop()
        self.key, self.path = key, path
        self.thumbnail = QImage()
        self.picture.clear()
        self.picture.setText("Loading…" if path else "—")
        if key in self.cache:
            self.cache.move_to_end(key)
            self._show(self.cache[key])
        elif path:
            self.debounce.start()

    def _show(self, image):
        self.thumbnail = image
        if image.isNull():
            self.picture.setText("Preview unavailable")
        else:
            self.picture.setPixmap(QPixmap.fromImage(image).scaled(self.picture.size(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _load(self):
        if self.closed or not self.key:
            return
        if self.key[1] is None:
            self.picture.setText("File missing")
            return
        if self.path.suffix.lower() not in VIDEO:
            self.job = _ImageJob(self.key)
            self.job.signals.ready.connect(self._image_ready)
            QThreadPool.globalInstance().start(self.job)
            return
        try:
            if PYSIDE2:
                from legacy_video import AudioOutput, VideoPlayer
                audio = AudioOutput(self)
                audio.setMuted(True)
                player = self.decoder = VideoPlayer(self.path, audio, self, thumbnail=True)
                audio.setParent(player)
                player.frameReady.connect(lambda frame: self._video_ready(player, frame))
                player.failed.connect(lambda _message: self._failed(player))
            else:
                from qtpy.QtMultimedia import QMediaPlayer, QVideoSink
                player = self.decoder = QMediaPlayer(self)
                sink = QVideoSink(player)
                player.setVideoSink(sink)
                # No QAudioOutput is attached: preview decoding cannot play sound.
                sink.videoFrameChanged.connect(lambda frame: self._qt_frame(player, frame),
                                                Qt.ConnectionType.QueuedConnection)
                player.errorOccurred.connect(lambda *_args: self._failed(player),
                                               Qt.ConnectionType.QueuedConnection)
                player.setSource(QUrl.fromLocalFile(str(self.path)))
            self.timeout.start()
            player.play()
        except (OSError, ValueError, RuntimeError):
            self._failed()

    def _qt_frame(self, player, frame):
        if player is not self.decoder or not frame.isValid():
            return
        image = frame.toImage()
        angle = frame.rotation().value
        if angle:
            image = image.transformed(QTransform().rotate(angle))
        if frame.mirrored():
            image = image.mirrored(True, False)
        self._video_ready(player, image)

    def _video_ready(self, player, image):
        if player is not self.decoder or image.isNull() or not self.thumbnail.isNull():
            return
        self._image_ready(self.key, image)
        # Never destroy a VLC decoder from inside its frame-delivery tick.
        QTimer.singleShot(0, lambda: self._release_if_current(player))

    def _image_ready(self, key, image):
        if self.closed or key != self.key:
            return
        self.timeout.stop()
        image = image.scaled(QSize(288, 162), Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation) if not image.isNull() else image
        self.cache[key] = image
        while len(self.cache) > 32:
            self.cache.popitem(last=False)
        self._show(image)

    def _failed(self, player=None):
        if player is not None and player is not self.decoder:
            return
        self.timeout.stop()
        self.picture.setText("Preview unavailable")
        current = self.decoder
        QTimer.singleShot(0, lambda: self._release_if_current(current))

    def _release_if_current(self, player):
        if player is self.decoder:
            self._release()

    def _release(self):
        self.timeout.stop()
        player, self.decoder = self.decoder, None
        if player:
            if PYSIDE2:
                player.close()
            else:
                player.stop()
                player.setVideoSink(None)
                player.setSource(QUrl())
            player.deleteLater()

    def shutdown(self):
        self.closed = True
        self.debounce.stop()
        self._release()
        self.cache.clear()
