"""Qt 6 PCM output with real gain above unity and bounded timestamped buffering.

The media player's one decoder supplies both video and PCM. No native audio
output is attached to it, so the amplified stream is the only audible stream.
All device operations and gain changes run on the GUI thread.
"""

from collections import deque
from time import monotonic

from qtpy.QtCore import QObject, QTimer, Qt, Signal
from qtpy.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioSink, QMediaDevices, QMediaPlayer

from audio_gain import pcm_gain
from audio_meter import pcm_peaks


class ModernAudio(QObject):
    peaks = Signal(object)
    failed = Signal(str)
    drained = Signal()

    def __init__(self, player, controls, parent=None):
        super().__init__(parent)
        self.player, self.controls = player, controls
        self.queue = deque()
        self.sink = self.device = None
        self.closed = self.running = False
        self.output_error = ""
        self.anchor = self.frozen = None
        self.last_pts = self.seek_target = None
        self.ending = False
        self.last_end = 0
        info = QMediaDevices.defaultAudioOutput()
        fmt = info.preferredFormat() if not info.isNull() else QAudioFormat()
        if not fmt.isValid():
            fmt.setSampleRate(48000)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.format = fmt
        self.sample_format = {QAudioFormat.SampleFormat.Int16: "s16", QAudioFormat.SampleFormat.Int32: "s32",
            QAudioFormat.SampleFormat.Float: "float", QAudioFormat.SampleFormat.UInt8: "u8"}[fmt.sampleFormat()]
        self.frame_bytes = fmt.bytesPerFrame()
        self.bytes_per_second = fmt.sampleRate() * self.frame_bytes
        if not info.isNull():
            self.sink = QAudioSink(info, fmt, self)
            self.sink.setBufferSize(self.bytes_per_second * 80 // 1000)
        self.tap = QAudioBufferOutput(self.format, self)
        self.tap.audioBufferReceived.connect(self.receive, Qt.ConnectionType.QueuedConnection)
        self.player.setAudioBufferOutput(self.tap)
        controls.changed.connect(self.apply_volume)
        player.playbackStateChanged.connect(self._state)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(5)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def apply_volume(self):
        if self.sink:
            # Gain is already applied to PCM exactly once. Hardware volume only
            # supplies immediate mute, including samples already in the device.
            self.sink.setVolume(0.0 if self.controls.isMuted() or self.controls.volume() == 0 else 1.0)

    def _state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.resume()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.pause()
        # EndOfMedia may still have the last few samples queued. Let those drain;
        # explicit Stop and source replacement call seek/close to discard them.

    def _clock(self):
        if self.anchor is None:
            return 0
        return self.anchor[0] + int((monotonic() - self.anchor[1]) * 1000000)

    def pause(self):
        if self.running:
            self.frozen = self._clock() if self.anchor else None
        self.running = False
        if self.sink and self.device:
            self.sink.suspend()

    def resume(self):
        if self.closed or self.running:
            return
        self.running = True
        if self.frozen is not None:
            self.anchor = (self.frozen, monotonic())
            self.frozen = None
        if self.sink and self.device:
            self.sink.resume()

    def seek(self, milliseconds):
        self.queue.clear()
        self.anchor = self.frozen = self.last_pts = None
        self.seek_target = max(0, int(milliseconds)) * 1000
        self.ending = False
        self.last_end = 0
        if self.sink:
            self.sink.reset()
        self.device = None
        # Keep the tap attached: replacing it while Qt is paused can disable
        # subsequent audio delivery. The timestamp gate rejects pre-seek data.

    def receive(self, buffer):
        if self.closed or not self.running or not buffer.isValid():
            return
        pts = buffer.startTime()
        if pts < 0:
            pts = self.last_pts if self.last_pts is not None else self.player.position() * 1000
        if self.seek_target is not None:
            if pts + buffer.duration() <= self.seek_target or pts > self.seek_target + 250000:
                return
            self.seek_target = None
        if self.last_pts is not None and pts < self.last_pts - 150000:
            # Native clip loop: retain the hardware tail, start a new cue clock.
            self.queue.clear()
            self.anchor = None
        if self.anchor is None:
            # One short pre-roll keeps the push device fed between GUI ticks.
            self.anchor = (pts - 20000, monotonic())
        self.last_pts = pts
        data = bytes(buffer.constData())[:buffer.byteCount()]
        self.last_end = pts + len(data) * 1000000 // self.bytes_per_second
        self.queue.append([pts, data, 0])
        while len(self.queue) > 200 or (len(self.queue) > 1 and self.queue[-1][0] - self.queue[0][0] > 2000000):
            self.queue.popleft()

    def render(self, data):
        gain = 0.0 if self.controls.isMuted() else self.controls.volume()
        return pcm_gain(data, gain, self.sample_format)

    def tick(self):
        if self.closed:
            return
        if not self.running:
            self._check_end()
            return
        now = self._clock()
        for _ in range(8):
            if not self.queue:
                break
            pts, data, offset = self.queue[0]
            end = pts + len(data) * 1000000 // self.bytes_per_second
            if end < now - 120000:
                self.queue.popleft()  # Drop stale sound after a stalled UI.
                continue
            queued = max(0, self.sink.bufferSize() - self.sink.bytesFree()) if self.device else 0
            due = pts + offset * 1000000 // self.bytes_per_second
            if due > now + queued * 1000000 // self.bytes_per_second:
                break
            if self.sink and self.device is None:
                self.device = self.sink.start()
                self.apply_volume()
                if self.device is None:
                    self.output_error = "The audio output device could not be opened."
                    self.failed.emit(self.output_error)
                    return
            size = min(len(data) - offset, max(0, self.sink.bytesFree())) if self.device else len(data) - offset
            size -= size % self.frame_bytes
            if not size:
                break
            raw = data[offset:offset + size]
            amplified = self.render(raw)
            written = self.device.write(amplified) if self.device else size
            if written <= 0:
                break
            self.queue[0][2] += written
            if self.queue[0][2] >= len(data):
                self.queue.popleft()
            self.peaks.emit(pcm_peaks(raw[:written], self.format.channelCount(), self.sample_format))
        self._check_end()

    def finish(self):
        self.ending = True
        self._check_end()

    def _check_end(self):
        queued = max(0, self.sink.bufferSize() - self.sink.bytesFree()) if self.device else 0
        if self.ending and not self.queue and not queued and (self.anchor is None or self._clock() >= self.last_end):
            self.ending = False
            self.running = False
            self.drained.emit()

    def close(self):
        self.closed = True
        self.timer.stop()
        self.queue.clear()
        self.controls.changed.disconnect(self.apply_volume)
        if self.sink:
            self.sink.reset()
        self.device = None
