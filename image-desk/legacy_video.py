"""VLC 3 video decoding for the Qt 5 / Python 3.8 Windows edition.

One decoder feeds both canvases. VLC's worker callbacks only copy bytes; Qt
objects and playback controls are accessed exclusively by the GUI timer.
"""

import ctypes
import os
import sys
import threading
from pathlib import Path
from time import monotonic

from qtpy.QtCore import QObject, QTimer, Signal
from qtpy.QtGui import QImage

# Load the app's private VLC, never a different version from the registry/PATH.
_dll_directory = None
_vlc_core = None
if sys.platform == "win32":
    _root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "vlc"
    if not (_root / "libvlc.dll").is_file():
        raise OSError("VLC libraries are missing. Extract the entire Image Desk ZIP before opening the app.")
    if hasattr(os, "add_dll_directory"):
        _dll_directory = os.add_dll_directory(str(_root))
    _vlc_core = ctypes.CDLL(str(_root / "libvlccore.dll"))
    os.environ["PYTHON_VLC_LIB_PATH"] = str(_root / "libvlc.dll")
    os.environ["PYTHON_VLC_MODULE_PATH"] = str(_root / "plugins")
    os.environ["VLC_PLUGIN_PATH"] = str(_root / "plugins")

import vlc

_instance = None


# libvlc_media_track_t contains an anonymous UNION. python-vlc 3.0.21203
# describes its three pointers as sequential fields; using track.video from
# that generated layout reads outside the union. Match the VLC 3 C ABI here.
class _TrackData(ctypes.Union):
    _fields_ = [("audio", ctypes.c_void_p), ("video", ctypes.POINTER(vlc.VideoTrack)),
                ("subtitle", ctypes.c_void_p)]


class _MediaTrack(ctypes.Structure):
    _fields_ = [("codec", ctypes.c_uint32), ("original_fourcc", ctypes.c_uint32),
                ("id", ctypes.c_int), ("type", ctypes.c_int), ("profile", ctypes.c_int),
                ("level", ctypes.c_int), ("data", _TrackData), ("bitrate", ctypes.c_uint),
                ("language", ctypes.c_char_p), ("description", ctypes.c_char_p)]


def instance():
    global _instance
    if _instance is None:
        # Software decoding works with older Windows drivers and supplies the
        # same frame to both displays without a second audio stream.
        _instance = vlc.Instance("--no-video-title-show", "--no-osd", "--no-spu",
                                 "--no-snapshot-preview", "--avcodec-hw=none",
                                 "--avcodec-threads=1",
                                 "--no-plugins-cache", "--file-caching=100", "--quiet")
        if _instance is None:
            raise ValueError("The bundled video decoder could not be started.")
    return _instance


class AudioOutput(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._volume = 0.8
        self._muted = False

    def setVolume(self, value):
        self._volume = max(0.0, min(1.0, float(value)))
        self.changed.emit()

    def volume(self):
        return self._volume

    def setMuted(self, value):
        self._muted = bool(value)
        self.changed.emit()

    def isMuted(self):
        return self._muted


class VideoPlayer(QObject):
    frameReady = Signal(QImage)
    playingChanged = Signal(bool)
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    seekableChanged = Signal(bool)
    metadataChanged = Signal(dict)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, path, audio, parent=None):
        super().__init__(parent)
        self.audio = audio
        self._media = instance().media_new_path(str(path))
        self._player = instance().media_player_new()
        self._player.set_media(self._media)
        self._closed = self._done = self._loop = self._has_frame = False
        self._has_audio = self._metadata = self._playing = self._seekable = False
        self._position = self._duration = 0
        self._restart_position = None
        self._seek_sent = None
        self._frame_size = None
        self._prepared = self._request_play = False
        self._audio_pending = False
        self._pause_after_seek = False
        self._latest = None
        self._callback_error = ""
        self._lock = threading.Lock()
        self._storage = None
        self._address = self._width = self._height = self._pitch = 0
        self._opened = monotonic()
        self._parse_started = monotonic()
        self._media.parse_with_options(vlc.MediaParseFlag.local, 2000)
        self._install_callbacks()
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)
        self.audio.changed.connect(self._apply_audio)

    def _install_callbacks(self):
        # c_void_p preserves the writable chroma pointer. c_char_p would turn it
        # into a temporary Python bytes object on entry to the callback.
        uint_p = ctypes.POINTER(ctypes.c_uint)
        format_type = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.c_void_p, uint_p, uint_p, uint_p, uint_p)

        @format_type
        def setup(_opaque, chroma, width, height, pitches, lines):
            try:
                # VLC's callback dimensions can include decoder padding (e.g.
                # ProRes 64x48 in a 64x64 allocation). Request the visible,
                # rotated dimensions from the parsed track metadata.
                w, h = self._frame_size or (int(width[0]), int(height[0]))
                width[0], height[0] = w, h
                if not (0 < w <= 16384 and 0 < h <= 16384) or w * h > 67108864:
                    raise ValueError("Video dimensions exceed this decoder's memory limit.")
                pitch, rows = (w * 4 + 31) & ~31, (h + 31) & ~31
                storage = ctypes.create_string_buffer(pitch * rows + 31)
                address = (ctypes.addressof(storage) + 31) & ~31
                with self._lock:
                    self._storage, self._address = storage, address
                    self._width, self._height, self._pitch = w, h, pitch
                ctypes.memmove(chroma, b"RV32", 4)
                pitches[0], lines[0] = pitch, rows
                return 1
            except Exception as error:
                self._callback_error = str(error)
                return 0

        @vlc.CallbackDecorators.VideoLockCb
        def lock(_opaque, planes):
            self._lock.acquire()
            planes[0] = self._address
            return None

        @vlc.CallbackDecorators.VideoUnlockCb
        def unlock(_opaque, _picture, _planes):
            self._lock.release()

        @vlc.CallbackDecorators.VideoDisplayCb
        def display(_opaque, _picture):
            try:
                with self._lock:
                    # Only one pending frame, so a slow UI cannot grow a queue.
                    pixels = ctypes.string_at(self._address, self._pitch * self._height)
                    self._latest = (pixels, self._width, self._height, self._pitch)
            except Exception as error:
                self._callback_error = str(error)

        self._callbacks = (setup, lock, unlock, display)  # Keep CFUNCTYPE objects alive.
        self._player.video_set_callbacks(lock, unlock, display, None)
        self._player.video_set_format_callbacks(setup, None)

    def _apply_audio(self):
        if not self._closed:
            self._player.audio_set_volume(round(self.audio.volume() * 100))
            self._player.audio_set_mute(self.audio.isMuted() or self._pause_after_seek)

    def hasAudio(self):
        return self._has_audio

    def setLoops(self, count):
        self._loop = count == -1

    def play(self, for_seek=False):
        if self._closed:
            return
        self._pause_after_seek = for_seek
        self._request_play = True
        if not self._prepared:
            self.timer.start()
            return
        if self._player.get_state() in (vlc.State.Ended, vlc.State.Error):
            self._player.stop()
        self._done = False
        self._audio_pending = True
        self._opened = monotonic()
        if self._player.play() == -1:
            self._error("The video could not be opened.")
            return
        self._apply_audio()
        self.timer.start()

    def pause(self):
        if not self._closed:
            self._request_play = False
            self._player.set_pause(1)
            self._set_playing(False)

    def setPosition(self, milliseconds):
        if self._closed:
            return
        value = max(0, int(milliseconds))
        if self._player.get_state() in (vlc.State.Ended, vlc.State.Stopped, vlc.State.NothingSpecial):
            self._restart_position = value
            self._seek_sent = None
            if self._prepared:
                # Decode the selected frame after EOF without resuming the
                # clip or playing a burst of audio. An explicit play() clears
                # this temporary pause request (e.g. the Restart button).
                self.play(for_seek=True)
        else:
            self._player.set_time(value)
        self._position = value
        self.positionChanged.emit(value)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        self.audio.changed.disconnect(self._apply_audio)
        self._media.parse_stop()
        # ctypes releases the GIL while stop waits for worker callbacks. Keep
        # buffers/callbacks alive until the decoder has completely stopped.
        self._player.stop()
        self._player.release()
        self._media.release()
        self._callbacks = ()
        self._storage = self._latest = None

    def _set_playing(self, value):
        if self._playing != value:
            self._playing = value
            self.playingChanged.emit(value)

    def _error(self, message):
        if self._done or self._closed:
            return
        self._done = True
        self.timer.stop()
        self._set_playing(False)
        self.failed.emit(message)

    def _read_metadata(self):
        # Use the C API directly so the returned track allocation can be freed.
        ptr = ctypes.POINTER(vlc.MediaTrack)()
        count = vlc.libvlc_media_tracks_get(self._media, ctypes.byref(ptr))
        if not count:
            return
        tracks = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(_MediaTrack)))
        info = {}
        try:
            for index in range(count):
                track = tracks[index].contents
                if track.type == vlc.TrackType.audio.value:
                    self._has_audio = True
                elif track.type == vlc.TrackType.video.value:
                    video = track.data.video.contents
                    w, h = video.width, video.height
                    if video.sar_num and video.sar_den:
                        w = max(1, round(w * video.sar_num / video.sar_den))
                    if video.orientation.value >= 4:
                        w, h = h, w
                    self._frame_size = (w, h)
                    rate = video.frame_rate_num / video.frame_rate_den if video.frame_rate_den else 0
                    codec = int(track.codec).to_bytes(4, "little").decode("ascii", "replace").strip("\0 ")
                    info = {"Frame rate": f"{rate:.3f} fps" if rate else "—", "Codec": codec or "—"}
        finally:
            vlc.libvlc_media_tracks_release(
                ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(vlc.MediaTrack))), count)
        if info:
            self._metadata = True
            self.metadataChanged.emit(info)

    def _tick(self):
        if self._closed:
            return
        if not self._prepared:
            status = self._media.get_parsed_status()
            if status in (vlc.MediaParsedStatus.done, vlc.MediaParsedStatus.failed,
                          vlc.MediaParsedStatus.skipped, vlc.MediaParsedStatus.timeout) or monotonic() - self._parse_started > 2.2:
                self._read_metadata()
                self._prepared = True
                if self._request_play:
                    self.play()
            else:
                return
        if self._callback_error:
            self._error(self._callback_error)
            return
        with self._lock:
            frame, self._latest = self._latest, None
        if frame:
            pixels, w, h, pitch = frame
            image = QImage(pixels, w, h, pitch, QImage.Format_RGB32).copy()
            self._has_frame = True
            self.frameReady.emit(image)
        state = self._player.get_state()
        if state == vlc.State.Playing and self._audio_pending:
            # Some audio outputs ignore settings until a stream exists.
            self._apply_audio()
            self._audio_pending = False
        if not self._metadata:
            self._read_metadata()
        duration = max(0, self._player.get_length())
        if duration and duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        seekable = self._seekable if state == vlc.State.Ended else bool(self._player.is_seekable())
        if seekable != self._seekable:
            self._seekable = seekable
            self.seekableChanged.emit(seekable)
        if state in (vlc.State.Playing, vlc.State.Paused) and seekable and self._restart_position is not None:
            if not self._pause_after_seek:
                self._player.set_time(self._restart_position)
                self._restart_position = None
            elif self._seek_sent is None or monotonic() - self._seek_sent > 0.1:
                # VLC initially reports the requested time before the input
                # thread has applied it. Confirm on a later tick; otherwise a
                # pause during startup can reset the displayed time to zero.
                if self._seek_sent is not None and abs(self._player.get_time() - self._restart_position) < 80:
                    self._restart_position = None
                else:
                    self._player.set_time(self._restart_position)
                    self._player.set_pause(1)
                    self._seek_sent = monotonic()
                    self._request_play = False
                    state = vlc.State.Paused
        position = self._restart_position if self._pause_after_seek and self._restart_position is not None else max(0, self._player.get_time())
        if position != self._position:
            self._position = position
            self.positionChanged.emit(position)
        if state == vlc.State.Error:
            self._error("The video could not be decoded. The file may be damaged or unsupported.")
        elif state == vlc.State.Ended:
            if not self._has_frame:
                self._error("This file contains no decodable video frames.")
            elif self._loop:
                self._player.stop()
                self._position = 0
                self.positionChanged.emit(0)
                self.play()
            elif not self._done:
                self._done = True
                self.timer.stop()
                self._set_playing(False)
                self.finished.emit()
        else:
            self._set_playing(state == vlc.State.Playing)
            if self._request_play and not self._has_frame and monotonic() - self._opened > 15:
                self._error("The video decoder did not produce a frame within 15 seconds.")
