"""PCM peak measurement and the operator's stereo dBFS meter."""

from array import array
import math
from time import monotonic

from qtpy.QtCore import QRectF, Qt, QTimer
from qtpy.QtGui import QColor, QLinearGradient, QPainter, QPen
from qtpy.QtWidgets import QWidget


def pcm_peaks(data, channels=2, sample_format="s16"):
    """Measure every sample, including negative full scale; no external DSP dependency."""
    code, scale, offset = {"s16": ("h", 32768.0, 0), "s32": ("i", 2147483648.0, 0),
                           "float": ("f", 1.0, 0), "u8": ("B", 128.0, 128)}[sample_format]
    samples = array(code)
    size = samples.itemsize
    samples.frombytes(bytes(data)[:len(data) // (size * channels) * size * channels])
    levels = []
    for channel in range(min(channels, 2)):
        levels.append(max((abs(value - offset) / scale for value in samples[channel::channels]
                           if math.isfinite(value)), default=0.0))
    if len(levels) == 1:
        levels *= 2
    return tuple(levels) if levels else (0.0, 0.0)


def dbfs(value):
    return max(-60.0, min(0.0, 20 * math.log10(value))) if value > 0 else -60.0


class AudioMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(120)
        self.setMinimumHeight(190)
        self.setAccessibleName("Stereo output audio level meter")
        self.setToolTip("L/R sample peaks in dBFS after item and master volume, before the system mixer. "
                        "Mono appears on both bars; multichannel files show front L/R. "
                        "Red indicates full-scale samples. Click to reset peak holds.")
        self.levels = [0.0, 0.0]
        self.display = [-60.0, -60.0]
        self.hold = [-60.0, -60.0]
        self.hold_until = [0.0, 0.0]
        self.clip_until = [0.0, 0.0]
        self.received = 0.0
        self.last_tick = monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.advance)
        self.timer.start()

    def set_levels(self, levels):
        self.levels = list(levels)
        self.received = monotonic()
        for i, value in enumerate(levels):
            level = dbfs(value)
            self.display[i] = max(self.display[i], level)
            if level >= self.hold[i]:
                self.hold[i], self.hold_until[i] = level, self.received + 1.5
            if value >= 0.999:
                self.clip_until[i] = self.received + 2.0
        self.update()

    def advance(self):
        now = monotonic()
        delta, self.last_tick = min(0.2, now - self.last_tick), now
        for i in range(2):
            target = dbfs(self.levels[i]) if now - self.received < 0.15 else -60.0
            self.display[i] = max(target, self.display[i] - 30 * delta)
            if now > self.hold_until[i]:
                self.hold[i] = max(self.display[i], self.hold[i] - 18 * delta)
        self.update()

    def mousePressEvent(self, event):
        self.hold = self.display.copy()
        self.clip_until = [0.0, 0.0]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#141924"))
        font = p.font()
        font.setPixelSize(10)
        p.setFont(font)
        top, bottom = 36, self.height() - 31
        height = bottom - top
        gradient = QLinearGradient(0, bottom, 0, top)
        for position, color in ((0, "#168b47"), (.65, "#1ee315"), (.8, "#a6ef00"),
                                 (.9, "#ffe219"), (.96, "#ff9d27"), (1, "#f04b4b")):
            gradient.setColorAt(position, QColor(color))
        p.setPen(QColor("#9ba8bd"))
        p.drawText(QRectF(0, 2, self.width(), 15), Qt.AlignmentFlag.AlignCenter, "AUDIO · dBFS")
        now = monotonic()
        for i in range(2):
            x = 9 + i * 30
            p.fillRect(QRectF(x, 21, 22, 7), QColor("#fa5555" if now < self.clip_until[i] else "#343644"))
            p.fillRect(QRectF(x, top, 22, height), QColor("#242c39"))
            y = top + height * -self.display[i] / 60
            if self.display[i] > -60:
                p.fillRect(QRectF(x, y, 22, bottom - y), gradient)
            if self.hold[i] > -60:
                y = top + height * -self.hold[i] / 60
                p.setPen(QPen(QColor("#eef3fa"), 1))
                p.drawLine(int(x), int(y), int(x + 22), int(y))
            p.setPen(QColor("#c7d2e5"))
            p.drawText(QRectF(x - 3, bottom + 3, 28, 13), Qt.AlignmentFlag.AlignCenter, "L" if i == 0 else "R")
            text = "−∞" if self.hold[i] <= -60 else f"{self.hold[i]:.1f}"
            p.drawText(QRectF(x - 4, bottom + 16, 32, 13), Qt.AlignmentFlag.AlignCenter, text)
        step = 3 if height >= 340 else 6
        for level in range(0, -61, -step):
            y = top + height * -level / 60
            p.setPen(QColor("#66758e"))
            p.drawLine(70, int(y), 74, int(y))
            p.setPen(QColor("#aab6c9"))
            p.drawText(QRectF(77, y - 7, 35, 14), Qt.AlignmentFlag.AlignLeft, str(level))
