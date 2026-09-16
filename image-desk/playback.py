"""One media clock and decoded frame stream for both Image Desk windows."""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QImage, QMovie, QTransform
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer, QVideoSink


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def clock_text(milliseconds: int) -> str:
    seconds = max(0, int(milliseconds)) // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


class Playback(QObject):
    frameReady = Signal(QImage)
    changed = Signal()
    metadataChanged = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "image"
        self.path = None
        self.player = None
        self.movie = None
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.loop = False
        self.playing = False
        self.ended = False
        self.error = ""
        self.position = 0
        self.duration = 0
        self.frame_count = 0
        self.seekable = False
        self.last_frame = QImage()
        self._gif_remaining = 0
        self._size = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._advance_gif)

    def clear(self):
        self.timer.stop()
        self.kind = "image"
        old, self.player = self.player, None
        if old:
            old.stop()
            old.setAudioOutput(None)
            old.setVideoSink(None)
            old.deleteLater()
        if self.movie:
            self.movie.deleteLater()
            self.movie = None
        self.path = None
        self.playing = self.ended = self.seekable = False
        self.error = ""
        self.position = self.duration = self.frame_count = self._gif_remaining = 0
        self._size = None
        self.last_frame = QImage()
        self.changed.emit()

    def load_video(self, path: Path):
        self.clear()
        self.kind, self.path = "video", path
        p = self.player = QMediaPlayer(self)
        sink = QVideoSink(p)
        p.setAudioOutput(self.audio)
        p.setVideoSink(sink)
        p.setLoops(-1 if self.loop else 1)
        # A new player per file also prevents queued frames from an old file
        # replacing the new image after quick Previous/Next operations.
        # Queue callbacks onto the GUI thread. Direct Python callbacks from the
        # decoder thread can deadlock a seek/stop while it waits for that thread.
        queued = Qt.ConnectionType.QueuedConnection
        sink.videoFrameChanged.connect(lambda frame: self._video_frame(p, frame), queued)
        p.playbackStateChanged.connect(lambda state: self._video_state(p, state), queued)
        p.positionChanged.connect(lambda value: self._video_position(p, value), queued)
        p.durationChanged.connect(lambda value: self._video_duration(p, value), queued)
        p.seekableChanged.connect(lambda value: self._video_seekable(p, value), queued)
        p.mediaStatusChanged.connect(lambda status: self._video_status(p, status), queued)
        p.metaDataChanged.connect(lambda: self._video_metadata(p), queued)
        p.errorOccurred.connect(lambda _code, text: self._video_error(p, text), queued)
        p.setSource(QUrl.fromLocalFile(str(path)))
        p.play()
        self.changed.emit()

    def load_gif(self, path: Path):
        movie = QMovie(str(path))
        if not movie.isValid() or not movie.jumpToFrame(0):
            movie.deleteLater()
            raise ValueError("This GIF could not be decoded.")
        self.clear()
        self.kind, self.path, self.movie = "gif", path, movie
        movie.setParent(self)
        # Drive frames ourselves: GIF-encoded loop counts must not override the
        # user's Play once / Loop setting. CacheNone keeps long GIFs bounded.
        self.frame_count = max(1, movie.frameCount())
        self.seekable = self.frame_count > 1
        self.playing = self.frame_count > 1
        self._publish_gif()
        self.metadataChanged.emit({"Format": "Animated GIF" if self.playing else "GIF",
                                   "Frames": f"{self.frame_count:,}"})
        self.changed.emit()

    def set_loop(self, loop: bool):
        self.loop = loop
        if self.player:
            self.player.setLoops(-1 if loop else 1)
        self.changed.emit()

    def toggle(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def pause(self):
        if self.kind == "video" and self.player:
            self.player.pause()
        elif self.kind == "gif":
            self._gif_remaining = max(1, self.timer.remainingTime())
            self.timer.stop()
            self.playing = False
            self.changed.emit()

    def play(self):
        if self.error:
            return
        if self.kind == "video" and self.player:
            if self.ended:
                self.player.setPosition(0)
            self.ended = False
            self.player.play()
        elif self.kind == "gif":
            if self.ended:
                self.restart()
                return
            self.playing = True
            self.timer.start(self._gif_remaining or max(10, self.movie.nextFrameDelay()))
            self._gif_remaining = 0
            self.changed.emit()

    def restart(self):
        if self.error:
            return
        self.ended = False
        if self.kind == "video" and self.player:
            self.player.setPosition(0)
            self.player.play()
        elif self.kind == "gif" and self.movie:
            self.timer.stop()
            self.playing = True
            self._gif_remaining = 0
            if self._gif_jump(0):
                self._publish_gif()
            else:
                self._fail("The GIF could not restart.")

    def seek(self, position: int):
        if not self.seekable or self.error:
            return
        self.ended = False
        if self.kind == "video" and self.player:
            self.player.setPosition(max(0, min(position, self.duration)))
        elif self.kind == "gif" and self.movie:
            self.timer.stop()
            self._gif_remaining = 0
            if self._gif_jump(max(0, min(position, self.frame_count - 1))):
                self._publish_gif()
            else:
                self._fail("This frame could not be read from the GIF.")

    def _publish_frame(self, image):
        if image.isNull():
            return
        self.last_frame = image
        size = (image.width(), image.height())
        if size != self._size:
            self._size = size
            self.metadataChanged.emit({"Dimensions": f"{size[0]:,} × {size[1]:,} pixels",
                                       "Color mode": "With transparency" if image.hasAlphaChannel() else "Opaque"})
        self.frameReady.emit(image)

    def _publish_gif(self):
        self.position = self.movie.currentFrameNumber()
        self._publish_frame(self.movie.currentImage())
        self.changed.emit()
        if self.playing:
            self.timer.start(max(10, self.movie.nextFrameDelay()))

    def _gif_jump(self, index):
        current = self.movie.currentFrameNumber()
        if index == current:
            return True
        if index == current + 1 and self.movie.jumpToFrame(index):
            return True
        # GIF decoders may only support sequential access with CacheNone.
        # Reopen for backwards/random seeks instead of caching every full frame.
        replacement = QMovie(str(self.path))
        for _ in range(index + 1):
            if not replacement.jumpToNextFrame():
                replacement.deleteLater()
                return False
        old, self.movie = self.movie, replacement
        replacement.setParent(self)
        old.deleteLater()
        return True

    def _advance_gif(self):
        if self.kind != "gif" or not self.playing:
            return
        next_frame = self.position + 1
        if next_frame >= self.frame_count:
            if self.loop:
                next_frame = 0
            else:
                self.ended, self.playing = True, False
                self.changed.emit()
                return
        if self._gif_jump(next_frame):
            self._publish_gif()
        else:
            self._fail("The GIF contains an unreadable frame.")

    def _video_frame(self, player, frame):
        if player is not self.player or not frame.isValid():
            return  # Keep the last good frame at the end of a clip.
        image = frame.toImage()
        angle = frame.rotation().value
        if angle:
            image = image.transformed(QTransform().rotate(angle))
        if frame.mirrored():
            image = image.mirrored(True, False)
        self._publish_frame(image)

    def _video_state(self, player, state):
        if player is self.player:
            self.playing = state == QMediaPlayer.PlaybackState.PlayingState
            self.changed.emit()

    def _video_position(self, player, value):
        if player is self.player:
            self.position = value
            self.changed.emit()

    def _video_duration(self, player, value):
        if player is self.player:
            self.duration = value
            self.metadataChanged.emit({"Duration": clock_text(value)})
            self.changed.emit()

    def _video_seekable(self, player, value):
        if player is self.player:
            self.seekable = value
            self.changed.emit()

    def _video_status(self, player, status):
        if player is not self.player:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended, self.playing = True, False
            self.changed.emit()

    def _video_metadata(self, player):
        if player is not self.player:
            return
        meta = player.metaData()
        rate = meta.value(QMediaMetaData.Key.VideoFrameRate)
        codec = meta.stringValue(QMediaMetaData.Key.VideoCodec)
        self.metadataChanged.emit({"Frame rate": f"{rate:.3f} fps" if rate else "—",
                                   "Codec": codec or "—"})

    def _video_error(self, player, text):
        if player is self.player:
            self._fail(text or "The video could not be decoded.")

    def _fail(self, text):
        self.error = text
        self.playing = False
        self.timer.stop()
        if self.player:
            self.player.pause()
        self.changed.emit()
        self.failed.emit(text)
