"""Timestamped VLC PCM output through Qt 5, with a tap for real sample peaks.

VLC callbacks only touch bounded byte queues. All Qt audio device calls happen
on the GUI thread; shutdown wakes a draining callback before waiting for VLC.
"""

from collections import deque
import ctypes
import threading
from time import monotonic

from qtpy.QtCore import QObject, QTimer, Qt, Signal
from qtpy.QtMultimedia import QAudio, QAudioDeviceInfo, QAudioFormat, QAudioOutput
from audio_meter import pcm_peaks


class LegacyAudio(QObject):
    peaks = Signal(object)

    def __init__(self, player, controls, vlc, parent=None):
        super().__init__(parent)
        self.controls, self.vlc = controls, vlc
        self.lock = threading.Lock()
        self.queue, self.commands = deque(), deque()
        self.closed = self.paused = False
        self.generation = 0
        self.drained = threading.Event()
        self.drained.set()
        self.pause_clock = self.last_end = 0
        self.sink = self.device = None
        self.output_error = ""
        self.silent = False
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleSize(16)
        fmt.setSampleType(QAudioFormat.SignedInt)
        fmt.setByteOrder(QAudioFormat.LittleEndian)
        fmt.setCodec("audio/pcm")
        info = QAudioDeviceInfo.defaultOutputDevice()
        if not info.isNull():
            if not info.isFormatSupported(fmt):
                fmt.setSampleRate(44100)
            if info.isFormatSupported(fmt):
                self.sink = QAudioOutput(info, fmt, self)
                self.sink.setBufferSize(fmt.sampleRate() * 4 // 10)
            else:
                self.output_error = "The audio device does not support stereo PCM output."
        self.rate, self.bytes_per_second = fmt.sampleRate(), fmt.sampleRate() * 4
        self._install(player)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _install(self, player):
        play_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int64)
        timed_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64)
        drain_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
        volume_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_float, ctypes.c_bool)

        @play_type
        def play(_opaque, samples, count, pts):
            if self.closed or count > self.rate * 2:
                return
            data = ctypes.string_at(samples, count * 4)
            levels = pcm_peaks(data)
            with self.lock:
                self.drained.clear()
                self.queue.append([pts, data, 0, levels])
                # Normally VLC queues < 200 ms. Bound a stalled UI to two seconds.
                while len(self.queue) > 200 or (len(self.queue) > 1 and self.queue[-1][0] - self.queue[0][0] > 2000000):
                    self.queue.popleft()

        @timed_type
        def pause(_opaque, pts):
            with self.lock:
                self.pause_clock = pts
                self.commands.append("pause")

        @timed_type
        def resume(_opaque, pts):
            with self.lock:
                shift = max(0, pts - self.pause_clock) if self.pause_clock else 0
                for block in self.queue:
                    block[0] += shift
                self.last_end += shift
                self.pause_clock = 0
                self.commands.append("resume")

        @timed_type
        def flush(_opaque, pts):
            self.discard()

        @drain_type
        def drain(_opaque):
            generation, deadline = self.generation, monotonic() + 3
            while not self.closed and generation == self.generation and monotonic() < deadline:
                if self.drained.wait(0.02):
                    break

        @volume_type
        def volume(_opaque, value, muted):
            # The Qt sink applies our linear item x master gain exactly once.
            pass

        self.callbacks = (play, pause, resume, flush, drain, volume)
        player.audio_set_callbacks(play, pause, resume, flush, drain, None)
        player.audio_set_format("S16N", self.rate, 2)
        player.audio_set_volume_callback(volume)

    def discard(self):
        with self.lock:
            self.queue.clear()
            self.generation += 1
            self.last_end = 0
            self.commands.append("flush")
            self.drained.set()

    def apply_volume(self, silent=None):
        if silent is not None:
            self.silent = silent
        if self.sink:
            self.sink.setVolume(0 if self.silent or self.controls.isMuted() else self.controls.volume())

    def tick(self):
        with self.lock:
            commands, self.commands = self.commands, deque()
        for command in commands:
            if command == "pause":
                self.paused = True
                if self.device:
                    self.sink.suspend()
            elif command == "resume":
                self.paused = False
                if self.device:
                    self.sink.resume()
            else:
                if self.sink:
                    self.sink.reset()
                self.device = None
        if self.paused or self.closed:
            return
        now = self.vlc.libvlc_clock()
        levels = None
        # Never hold the queue lock across a Qt call or signal delivery.
        with self.lock:
            block = self.queue[0] if self.queue else None
        if block:
            pts, data, offset, peaks = block
            queued = max(0, self.sink.bufferSize() - self.sink.bytesFree()) if self.device else 0
            due = pts + offset * 1000000 // self.bytes_per_second
            if due <= now + queued * 1000000 // self.bytes_per_second + 10000:
                if self.sink and self.device is None:
                    self.device = self.sink.start()
                    self.apply_volume()
                    if self.device is None:
                        self.output_error = "The audio output device could not be opened."
                size = min(len(data) - offset, max(0, self.sink.bytesFree())) if self.device else len(data) - offset
                size -= size % 4
                written = self.device.write(data[offset:offset + size]) if self.device and size else size
                if written > 0:
                    levels = peaks
                    with self.lock:
                        if self.queue and self.queue[0] is block:
                            block[2] += written
                            self.last_end = pts + len(data) * 1000000 // self.bytes_per_second
                            if block[2] >= len(data):
                                self.queue.popleft()
        if levels is not None:
            self.peaks.emit(levels)
        with self.lock:
            empty = not self.queue
        if empty and now >= self.last_end:
            self.drained.set()

    def close(self):
        self.closed = True
        self.drained.set()
        self.timer.stop()
        if self.sink:
            self.sink.stop()
        with self.lock:
            self.queue.clear()
