"""Integration checks for meters, gain, scrubbing and playlist clocks."""

from array import array
import json

from qtpy import PYSIDE2
from qtpy.QtCore import QEvent, QPoint, QPointF, Qt
from qtpy.QtGui import QMouseEvent
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication

from audio_meter import pcm_peaks
from playlist_data import PlaylistData
from session import read_session


def drag_to(widget, point):
    # Qt 5's QTest.mouseMove only moves the platform cursor; the offscreen
    # plugin never delivers that motion. Send the same real mouse-move event
    # that a window receives, with the left button still held.
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), Qt.MouseButton.NoButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def run_checks(window, root, wait, until, checks):
    p, c, panel = window.playback, window.playlist, window.playlist_panel
    c.stop()
    c.replace_playlists([PlaylistData("Audio test")])
    window.volume_slider.setValue(100)
    window.mute_button.setChecked(False)
    p.audio.setMuted(False)
    p.set_loop(True)
    measured = []
    p.audioLevels.connect(measured.append)
    assert pcm_peaks(array("h", [-32768, 8192, 16384, -4096]).tobytes()) == (1.0, 0.25)
    assert pcm_peaks(array("f", [0.5, -0.25, float("nan"), 0]).tobytes(), 2, "float") == (0.5, 0.25)
    assert pcm_peaks(array("h", [-16384, 8192]).tobytes(), 1) == (0.5, 0.5)
    assert window.load_image(root / "stereo.mp4")
    until(lambda: p.playing and max(p.raw_levels) > 0.3)
    assert 0.40 < p.raw_levels[0] < 0.65 and 0.08 < p.raw_levels[1] < 0.20, p.raw_levels
    assert any(left > right * 2 for left, right in measured)
    window.volume_slider.setValue(50)
    p.set_item_volume(0.5)
    wait(100)
    assert abs(p.audio.volume() - .25) < .001
    assert 0.08 < measured[-1][0] < .17, measured[-1]
    window.mute_button.setChecked(True)
    assert measured[-1] == (0.0, 0.0)
    window.mute_button.setChecked(False)
    window.pause_button.click()
    until(lambda: not p.playing)
    assert measured[-1] == (0.0, 0.0)
    if PYSIDE2 and p.player.audio_bridge.sink:
        assert not p.player.audio_bridge.output_error, p.player.audio_bridge.output_error
    checks.append("Measured asymmetric stereo PCM, negative full scale, mono, master x item gain, mute and pause metering")

    # Duplicate paths are separate entries; settings travel with rows and persist.
    c.set_items([root / "stereo.mp4", root / "stereo.mp4", root / "still.png"])
    panel.list.setCurrentRow(0)
    panel.item_volume.setValue(25)
    panel.list.setCurrentRow(1)
    panel.item_volume_slider.setValue(75)
    c.move(0, 1)
    assert c.current_playlist.volumes == [75, 25, 100]
    c.remove([2])
    session = root / "Audio-levels.imagedesk.json"
    window.save_session_file(session)
    loaded, selected, settings = read_session(session)
    assert loaded[0].volumes == [75, 25] and settings["volume"] == 50
    raw = json.loads(session.read_text())
    for value in ([110, 25], [True, 25], [75], "invalid"):
        raw["playlists"][0]["volumes"] = value
        session.write_text(json.dumps(raw))
        try:
            read_session(session)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid per-item volumes accepted")
    raw["version"] = 2
    raw["playlists"][0].pop("volumes")
    session.write_text(json.dumps(raw))
    assert read_session(session)[0][0].volumes == [100, 100]
    c.start(0)
    until(lambda: p.playing)
    assert abs(p.audio.volume() - .375) < .001
    panel.item_volume.setValue(60)
    assert abs(p.audio.volume() - .3) < .001 and window.volume_slider.value() == 50
    window.next_button.click()
    until(lambda: c.index == 1 and p.playing)
    assert abs(p.audio.volume() - .125) < .001
    window.previous_button.click()
    until(lambda: c.index == 0 and p.playing)
    window.pause_button.click()
    until(lambda: c.paused and not p.playing)
    window.play_button.click()
    until(lambda: not c.paused and p.playing)
    c.stop()
    window.load_image(root / "stereo.mp4")
    assert p.item_volume == 1.0 and window.volume_slider.value() == 50
    checks.append("Independent duplicate-item volumes survive move/remove/save; legacy sessions default to 100%; transport and live gain")

    # Exercise real pointer events and verify frames change before mouse release.
    p.set_loop(False)
    until(lambda: p.seekable and p.playing)
    window.pause_button.click()
    until(lambda: not p.playing)
    slider = window.seek_slider
    width, y = slider.width(), slider.height() // 2
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(width // 5, y))
    wait(180)
    first = p.last_frame.copy()
    drag_to(slider, QPoint(width * 3 // 5, y))
    until(lambda: p.position > 1500)
    wait(180)
    assert window._seeking and not p.playing
    assert p.last_frame != first, "Dragging did not update the preview before release"
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(width * 3 // 5, y))
    wait(100)
    assert not p.playing and not window._seeking
    c.set_items([root / "stereo.mp4", root / "still.png"])
    c.start()
    until(lambda: p.playing and p.seekable)
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(width // 4, y))
    drag_to(slider, QPoint(width // 2, y))
    wait(150)
    assert c.paused and c.index == 0
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(width // 2, y))
    until(lambda: p.playing and not c.paused)
    assert c.index == 0
    c.stop()
    checks.append("Pointer dragging changes decoded preview frames before release, preserves paused state, and resumes active playlists")

    c.set_items([root / "still.png", root / "stereo.mp4", root / "once.gif"])
    panel.seconds.setValue(2.0)
    until(lambda: window.playlist_remaining_milliseconds()[2] == 0)
    total, unknown, pending = window.playlist_remaining_milliseconds()
    assert 5300 <= total <= 5500 and unknown == pending == 0, (total, unknown, pending)
    c.start()
    wait(150)
    c.pause()
    frozen = window.playlist_remaining_milliseconds()[0]
    wait(180)
    assert window.playlist_remaining_milliseconds()[0] == frozen
    c.step(1)
    until(lambda: p.playing and p.duration > 0)
    c.pause()
    until(lambda: not p.playing)
    p.seek(1800)
    until(lambda: abs(p.position - 1800) < 80)
    remaining = window.playlist_remaining_milliseconds()[0]
    assert 1500 <= remaining <= 1700, remaining
    panel.repeat.setChecked(True)
    window.update_countdown()
    assert "this pass" in window.playlist_remaining_hint.text()
    c.step(1)
    c.pause()
    gif_remaining = window.remaining_milliseconds()
    assert 250 <= gif_remaining <= 500, gif_remaining
    wait(100)
    assert window.remaining_milliseconds() == gif_remaining
    c.stop()
    c.set_items([root / "missing.mp4", root / "invalid.mp4", root / "still.png"])
    until(lambda: window.playlist_remaining_milliseconds()[2] == 0)
    assert window.playlist_remaining_milliseconds() == (2000, 1, 0)
    window.update_countdown()
    assert "+ ?" in window.playlist_remaining_label.text()
    checks.append("Playlist total includes video, GIF and still durations; pause/seek/repeat clocks stay accurate and unknown durations are explicit")
    p.audioLevels.disconnect(measured.append)
