"""Checks actual rendered PCM, gain persistence and the compact 0–200% editor."""

from array import array
import json
from time import monotonic

from qtpy import PYSIDE2
from qtpy.QtWidgets import QStyle, QStyleOptionSlider

from audio_gain import pcm_gain
from audio_meter import pcm_peaks
from playlist_data import PlaylistData
from session import read_session


class RecordingSink:
    """A clocked output device, so CI exercises real writes without speakers."""
    def __init__(self, rate):
        self.rate = rate
        self.capacity = rate * 80 // 1000
        self.pending = self.written = 0
        self._volume = 1.0
        self.suspended = False
        self.last = monotonic()

    def _drain(self):
        now = monotonic()
        if not self.suspended:
            self.pending = max(0, self.pending - int((now - self.last) * self.rate))
        self.last = now

    def start(self):
        self.suspended = False
        self.last = monotonic()
        return self

    def write(self, data):
        self.written += len(data)
        self.pending += len(data)
        return len(data)

    def bufferSize(self):
        return self.capacity

    def bytesFree(self):
        self._drain()
        return max(0, self.capacity - self.pending)

    def setVolume(self, value):
        self._volume = value

    def volume(self):
        return self._volume

    def suspend(self):
        self._drain()
        self.suspended = True

    def resume(self):
        self.last = monotonic()
        self.suspended = False

    def reset(self):
        self.pending = 0
        self.suspended = False
        self.last = monotonic()

    def stop(self):
        self.reset()


def run_checks(window, root, wait, until, checks):
    p, c, panel = window.playback, window.playlist, window.playlist_panel
    c.stop()
    c.replace_playlists([PlaylistData("Boost test")])
    window.add_playlist_files([root / "stereo.mp4", root / "stereo.mp4"])
    assert c.current_playlist.volumes == [100, 100]
    panel.list.setCurrentRow(0)
    slider = panel.item_volume_slider
    assert (slider.minimum(), slider.maximum(), slider.value()) == (0, 200, 100)
    assert slider.width() == 220 and window.volume_slider.maximum() == 100
    option = QStyleOptionSlider()
    slider.initStyleOption(option)
    handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                          QStyle.SubControl.SC_SliderHandle, slider)
    assert abs(handle.center().x() - slider.rect().center().x()) <= 2
    raw = array("h", [24576, -24576, 8192, -8192]).tobytes()
    assert list(array("h", pcm_gain(raw, 2))) == [32767, -32768, 16384, -16384]
    # Combine gains before saturation: 200% item x 50% master is unchanged PCM.
    p.set_item_volume(2)
    p.set_master_volume(.5)
    assert pcm_gain(raw, p.audio.volume()) == raw
    assert list(pcm_gain(bytes([128, 160, 96, 255]), 2, "u8")) == [128, 192, 64, 255]
    f = array("f", [.25, -.75, float("nan")]).tobytes()
    assert list(array("f", pcm_gain(f, 2, "float"))) == [.5, -1, 0]
    i32 = array("i", [1073741824, -1610612736]).tobytes()
    assert list(array("i", pcm_gain(i32, 2, "s32"))) == [2147483647, -2147483648]
    checks.append("Compact item slider defaults to centered 100%; 200% PCM doubles amplitude and saturates safely in all sample formats")

    window.volume_slider.setValue(100)
    window.mute_button.setChecked(False)
    p.audio.setMuted(False)
    c.start()
    until(lambda: p.playing and max(p.raw_levels) > .3)
    window.repeat_combo.setCurrentIndex(1)
    player, bridge = p.player, p.player.audio_bridge
    if not PYSIDE2:
        assert player.audioOutput() is None and player.audioBufferOutput() is bridge.tap
    captured = []
    original_sink = bridge.sink
    if original_sink:
        original_sink.reset()
    bridge.sink = RecordingSink(bridge.bytes_per_second)
    bridge.device = None
    original = bridge.render
    fmt = "s16" if PYSIDE2 else bridge.sample_format
    channels = 2 if PYSIDE2 else bridge.format.channelCount()

    def capture(data):
        result = original(data)
        captured.append((pcm_peaks(data, channels, fmt), pcm_peaks(result, channels, fmt)))
        del captured[:-30]
        return result

    bridge.render = capture

    def verify(gain):
        captured.clear()
        before = bridge.sink.written
        until(lambda: len(captured) >= 4)
        assert bridge.sink.written > before
        for raw_levels, output_levels in captured[-3:]:
            assert all(abs(output_levels[i] - min(1.0, raw_levels[i] * gain)) < .002
                       for i in range(2)), (gain, raw_levels, output_levels)
        assert p.player is player
        assert bridge.sink.volume() == (0 if p.audio.isMuted() else 1)

    verify(1)
    panel.item_volume_slider.setValue(200)
    assert panel.item_volume.value() == 200 and panel.boost_label.text() == "Boost"
    assert p.audio.volume() == 2 and p.item_volume == 2
    verify(2)
    window.volume_slider.setValue(50)
    verify(1)
    window.volume_slider.setValue(80)
    verify(1.6)
    window.mute_button.setChecked(True)
    verify(0)
    window.mute_button.setChecked(False)
    verify(1.6)
    window.pause_button.click()
    until(lambda: not p.playing)
    count = bridge.sink.written
    wait(150)
    assert bridge.sink.written == count
    window.seek_slider.setValue(1400)
    until(lambda: abs(p.position - 1400) < 100)
    wait(100)
    assert bridge.sink.written == count
    window.play_button.click()
    until(lambda: p.playing)
    verify(1.6)
    window.stop_button.click()
    until(lambda: not p.playing)
    count = bridge.sink.written
    wait(150)
    assert bridge.sink.written == count
    bridge.render = original
    bridge.sink = original_sink
    bridge.device = None
    checks.append("The real decoder output applies 200% boost once; master/mute work live, paused seeks stay silent, and Stop silences output")

    session = root / "Boosted.imagedesk.json"
    window.save_session_file(session)
    data = json.loads(session.read_text())
    assert data["version"] == 4
    loaded, _, settings = read_session(session)
    assert loaded[0].volumes == [200, 100] and settings["volume"] == 80
    for value in (201, -1, True, 150.5):
        bad = json.loads(json.dumps(data))
        bad["playlists"][0]["volumes"][0] = value
        session.write_text(json.dumps(bad))
        try:
            read_session(session)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid boosted gain accepted")
    session.write_text(json.dumps(data))
    assert window.open_session_file(session, quiet=True)
    c.start()
    until(lambda: p.playing)
    assert p.item_volume == 2 and abs(p.audio.volume() - 1.6) < .0001
    window.next_button.click()
    until(lambda: c.index == 1 and p.playing)
    assert p.item_volume == 1 and p.audio.volume() == .8
    c.stop()
    c.move(0, 1)
    assert c.current_playlist.volumes == [100, 200]
    c.remove([1])
    window.save_session_file(session)
    assert json.loads(session.read_text())["version"] == 3
    assert read_session(session)[0][0].volumes == [100]
    checks.append("Boosted sessions round-trip at format 4; normal sessions remain format 3; gains follow duplicate rows and new entries stay at 100%")
