"""Asynchronous duration lookup; probing never starts a second audible player."""

from collections import deque
from pathlib import Path
from time import monotonic

from qtpy import PYSIDE2
from qtpy.QtCore import QObject, QRunnable, QSize, QThreadPool, QTimer, QUrl, Signal
from qtpy.QtGui import QImageReader

VIDEO = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


class _Signals(QObject):
    done = Signal(str, object)


class _GifJob(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = _Signals()

    def run(self):
        delays = []
        reader = QImageReader(self.path)
        reader.setScaledSize(QSize(1, 1))
        count = reader.imageCount()
        # Match QMovie's decoder timing, without keeping full-sized frames.
        for _ in range(max(1, count)):
            if reader.read().isNull():
                delays = []
                break
            delays.append(max(10, reader.nextImageDelay()))
        self.signals.done.emit(self.path, delays or None)


class MediaCatalog(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = {}
        self.queue = deque()
        self._queued = set()
        self.current = None
        self.player = self.media = self.job = None
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._poll)

    @staticmethod
    def stamp(path):
        try:
            stat = Path(path).stat()
            return stat.st_size, stat.st_mtime_ns
        except OSError:
            return None

    def ensure(self, paths):
        if self.closed:
            return
        for path in paths:
            key = str(path)
            stamp = self.stamp(path)
            if key in self.entries and self.entries[key][0] == stamp:
                continue
            if key not in self._queued and key != self.current:
                self.entries.pop(key, None)
                self.queue.append(key)
                self._queued.add(key)
        if not self.current:
            QTimer.singleShot(0, self._next)

    def info(self, path):
        entry = self.entries.get(str(path))
        return entry[1] if entry else None

    def remember_video(self, path, duration):
        if path and duration > 0:
            self.entries[str(path)] = (self.stamp(path), {"duration": duration, "delays": None})

    def _next(self):
        if self.closed or self.current:
            return
        while self.queue:
            self.current = self.queue.popleft()
            self._queued.discard(self.current)
            path = Path(self.current)
            self._stamp = self.stamp(path)
            if self.current in self.entries:
                self.current = None
                continue
            if self._stamp is None:
                self._finish({"duration": 0, "missing": True})
                return
            if path.suffix.lower() == ".gif":
                self.job = _GifJob(self.current)
                self.job.signals.done.connect(self._gif_done)
                QThreadPool.globalInstance().start(self.job)
                return
            if path.suffix.lower() not in VIDEO:
                self._finish({"still": True})
                return
            self.started = monotonic()
            if PYSIDE2:
                from legacy_video import instance, vlc
                self.media = instance().media_new_path(self.current)
                self.media.parse_with_options(vlc.MediaParseFlag.local, 3000)
            else:
                from qtpy.QtMultimedia import QMediaPlayer
                self.player = QMediaPlayer(self)
                self.player.setSource(QUrl.fromLocalFile(self.current))
            self.timer.start()
            return

    def _gif_done(self, path, delays):
        if self.closed or path != self.current:
            return
        if delays:
            self._finish({"duration": sum(delays), "delays": delays, "still": len(delays) == 1})
        else:
            self._finish({"unknown": True})

    def _poll(self):
        if PYSIDE2:
            from legacy_video import vlc
            duration = self.media.get_duration()
            ready = self.media.get_parsed_status() in (vlc.MediaParsedStatus.done,
                     vlc.MediaParsedStatus.failed, vlc.MediaParsedStatus.timeout, vlc.MediaParsedStatus.skipped)
        else:
            from qtpy.QtMultimedia import QMediaPlayer
            duration = self.player.duration()
            ready = self.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                                                  QMediaPlayer.MediaStatus.InvalidMedia)
        if duration > 0:
            self._finish({"duration": duration, "delays": None})
        elif ready or monotonic() - self.started > 4:
            self._finish({"unknown": True})

    def _release(self):
        self.timer.stop()
        if self.player:
            self.player.setSource(QUrl())
            self.player.deleteLater()
            self.player = None
        if self.media:
            self.media.parse_stop()
            self.media.release()
            self.media = None

    def _finish(self, value):
        self.entries[self.current] = (self._stamp, value)
        self._release()
        self.current = self.job = None
        self.changed.emit()
        QTimer.singleShot(0, self._next)

    def close(self):
        self.closed = True
        self.queue.clear()
        self._release()
