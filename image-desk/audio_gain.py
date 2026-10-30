"""Shared linear PCM gain, with saturation instead of integer wraparound."""

from array import array
import audioop
import math

from qtpy.QtCore import QObject, Signal


def pcm_gain(data, gain, sample_format="s16"):
    """Apply item x master once; 2.0 doubles amplitude (+6.02 dB)."""
    gain = max(0.0, min(2.0, float(gain)))
    data = bytes(data)
    if gain == 1.0:
        return data
    if sample_format == "float":
        values = array("f")
        values.frombytes(data)
        return array("f", (max(-1.0, min(1.0, value * gain)) if math.isfinite(value)
                           else 0.0 for value in values)).tobytes()
    if sample_format == "u8":
        return audioop.bias(audioop.mul(audioop.bias(data, 1, -128), 1, gain), 1, 128)
    return audioop.mul(data, {"s16": 2, "s32": 4}[sample_format], gain)


class AudioControls(QObject):
    """Output controls independent of Qt's 100%-limited hardware volume API."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._volume = .8
        self._muted = False

    def setVolume(self, value):
        value = float(value)
        self._volume = max(0.0, min(2.0, value)) if math.isfinite(value) else 0.0
        self.changed.emit()

    def volume(self):
        return self._volume

    def setMuted(self, value):
        self._muted = bool(value)
        self.changed.emit()

    def isMuted(self):
        return self._muted
