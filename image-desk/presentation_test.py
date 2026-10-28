"""Native integration checks for playlist timing, output controls and sessions."""

import base64
import json
import shutil

from qtpy.QtCore import QRect, QTimer
from qtpy.QtGui import QColor, QImage, QPainter, QPixmap
from qtpy.QtWidgets import QApplication, QInputDialog


def run_checks(window, root, wait, until, checks):
    p, c = window.playback, window.playlist
    panel = window.playlist_panel
    seen = []

    def record():
        if c.active and (not seen or seen[-1] != c.index):
            seen.append(c.index)

    c.changed.connect(record)
    panel.seconds.setValue(0.5)
    panel.repeat.setChecked(False)
    p.set_loop(True)
    c.set_items([root / n for n in ("still.png", "sample.mp4", "once.gif", "sample.mov", "still.png")])
    c.start()
    assert c.active and not p.loop
    until(lambda: not c.active)
    assert seen == [0, 1, 2, 3, 4], seen
    assert c.status == "Finished" and p.loop and window.current_path == root / "still.png", (
        c.status, p.loop, str(window.current_path), str(root / "still.png"))
    assert window.remaining_milliseconds() == 0
    checks.append("Mixed playlist advances in order, times stills, holds final item and restores clip-loop mode")

    panel.seconds.setValue(1.0)
    c.set_items([root / "still.png", root / "once.gif"])
    c.start()
    wait(200)
    window.space_pressed()
    remaining = window.remaining_milliseconds()
    wait(250)
    assert c.paused and c.index == 0 and window.remaining_milliseconds() == remaining
    window.output_timer_check.setChecked(True)
    window.toggle_presentation()
    canvas = window.presentation.canvas
    window.blackout_button.setChecked(True)
    window.update_countdown()
    assert canvas.countdown_text.endswith("remaining")
    black = canvas.grab().toImage()
    assert black.pixelColor(black.width() // 2, black.height() // 2).name() == "#000000"
    preview = window.preview.grab().toImage()
    assert preview.pixelColor(preview.width() // 2, preview.height() // 2).name() == "#123456"
    window.space_pressed()
    until(lambda: c.index == 1)
    assert canvas.blackout and window.blackout
    until(lambda: not c.active)
    assert canvas.blackout  # Blackout persists across automatic transitions.
    window.blackout_button.setChecked(False)
    output = canvas.grab().toImage()
    assert output.pixelColor(output.width() // 2, output.height() // 2).name() == "#0000ff"
    window.presentation.close()
    checks.append("Still countdown pauses accurately; blackout keeps preview visible and survives playlist advances")

    panel.seconds.setValue(0.5)
    panel.repeat.setChecked(True)
    c.set_items([root / "still.png", root / "still.png"])
    seen.clear()
    c.start()
    until(lambda: len(seen) >= 3)
    assert seen[:3] == [0, 1, 0], seen
    c.pause()
    index = c.index
    wait(650)
    assert c.active and c.paused and c.index == index
    c.stop()
    checks.append("Repeat playlist wraps and pauses without advancing")

    panel.repeat.setChecked(False)
    c.set_items([root / "sample.mp4"])
    c.start()
    until(lambda: p.position >= 100)
    window.play_button.click()
    until(lambda: not p.playing)
    assert c.paused and c.active
    window.seek_slider.setValue(350)
    until(lambda: abs(p.position - 350) < 80)
    assert c.paused
    window.restart_button.click()
    until(lambda: p.position >= 100)
    assert c.active and not c.paused
    window.load_image(root / "still.png")
    wait(850)
    assert not c.active and window.current_path == root / "still.png"
    checks.append("Playlist transport pauses, seeks and restarts; manual media cancels queued advances")

    c.set_items([root / "missing.mp4", root / "invalid.mp4", root / "still.png"])
    c.start()
    until(lambda: not c.active)
    assert c.index == 2 and c.status == "Finished"
    panel.repeat.setChecked(True)
    c.set_items([root / "missing.mp4", root / "invalid.mp4"])
    c.start()
    until(lambda: not c.active)
    assert c.status == "No playable items"
    checks.append("Missing/corrupt items are skipped and an entirely invalid repeating playlist stops")

    static = root / "static.gif"
    static.write_bytes(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"))
    panel.repeat.setChecked(False)
    c.set_items([static, root / "still.png"])
    c.start()
    assert p.frame_count == 1 and window.remaining_milliseconds() > 0
    until(lambda: not c.active)
    assert c.index == 1
    checks.append("Single-frame GIFs use the still-image timer")

    c.set_items([root / "sample.mov", root / "still.png", root / "once.gif", root / "missing.mp4"])
    assert c.move(2, -1) == 1
    c.remove([0])
    assert [path.name for path in c.paths] == ["once.gif", "still.png", "missing.mp4"]
    panel.seconds.setValue(2.5)
    panel.repeat.setChecked(True)
    window.repeat_combo.setCurrentIndex(1)
    p.set_loop(True)
    window.mode_combo.setCurrentText("Fill")
    window.output_timer_check.setChecked(True)
    window.volume_slider.setValue(37)
    window.mute_button.setChecked(True)
    expected = window.session_settings()
    session = root / "Show.imagedesk.json"
    window.save_session_file(session)
    data = json.loads(session.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert data["playlists"][0]["items"] == ["once.gif", "still.png", "missing.mp4"]
    moved = root / "moved-show"
    moved.mkdir()
    for name in ("once.gif", "still.png", session.name):
        shutil.copy2(root / name, moved / name)
    panel.seconds.setValue(8)
    panel.repeat.setChecked(False)
    window.volume_slider.setValue(90)
    assert window.open_session_file(moved / session.name, quiet=True)
    assert window.session_settings() == expected
    assert all(path.parent == moved for path in c.paths)
    assert not c.active and p.player is None and window.current_path is None
    assert "missing" in panel.list.item(2).text()
    malformed = root / "invalid.imagedesk.json"
    malformed.write_text('{"format":"image-desk-session","version":1,"items":[],"settings":{"still_seconds":-1}}')
    before = c.paths.copy()
    assert not window.open_session_file(malformed, quiet=True)
    assert c.paths == before and window.session_settings() == expected
    checks.append("Reorder/remove, portable session round-trip, saved settings, missing-file labels and invalid-session recovery")
    c.changed.disconnect(record)
    run_collection_checks(window, root, wait, until, checks)


def run_collection_checks(window, root, wait, until, checks):
    p, c, panel = window.playback, window.playlist, window.playlist_panel
    canvas = type(window.preview)("#121212")
    canvas.resize(400, 300)
    canvas.show()
    media = QImage(200, 100, QImage.Format.Format_RGB32)
    media.fill(QColor("#2a6dc0"))
    painter = QPainter(media)
    painter.fillRect(QRect(0, 0, 40, 30), QColor("#f5c242"))
    painter.end()
    canvas.set_image(QPixmap.fromImage(media))

    def pixel(x, y):
        shot = canvas.grab().toImage()
        ratio = shot.devicePixelRatio()
        return shot.pixelColor(int(x * ratio), int(y * ratio)).name()

    for mode in ("Fit", "Fill", "Actual size"):
        canvas.set_mode(mode)
        canvas.set_alignment("Top left")
        assert pixel(0, 0) == "#f5c242", mode
        canvas.set_alignment("Center")
        if mode == "Fill":
            assert pixel(30, 5) == "#2a6dc0"
        else:
            assert pixel(0, 0) == "#121212", mode
            x, y = (5, 55) if mode == "Fit" else (105, 105)
            assert pixel(x, y) == "#f5c242", mode
    canvas.close()
    window.load_image(root / "sample.mp4")
    until(lambda: not p.last_frame.isNull())
    window.toggle_presentation()
    same_player = p.player
    window.alignment_combo.setCurrentIndex(window.alignment_combo.findData("Center"))
    wait(100)
    assert p.player is same_player and p.playing
    assert window.preview.alignment == window.presentation.canvas.alignment == "Center"
    window.blackout_button.setChecked(True)
    window.alignment_combo.setCurrentIndex(window.alignment_combo.findData("Top left"))
    assert window.presentation.canvas.blackout
    assert window.presentation.canvas.grab().toImage().pixelColor(0, 0).name() == "#000000"
    window.blackout_button.setChecked(False)
    window.alignment_combo.setCurrentIndex(window.alignment_combo.findData("Center"))
    window.presentation.close()
    window.load_image(root / "once.gif")
    assert window.preview.alignment == "Center"
    window.load_image(root / "still.png")
    assert window.preview.alignment == "Center"
    checks.append("Top-left/center rendering in Fit, Fill and Actual size; live alignment preserves shared playback and blackout")

    def name_dialog(button, name):
        def fill_dialog():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QInputDialog):
                dialog.setTextValue(name)
                dialog.accept()
        QTimer.singleShot(100, fill_dialog)
        # Bound a failed dialog check so the packaged test can still report it.
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: QApplication.activeModalWidget().reject()
                              if QApplication.activeModalWidget() else None)
        guard.start(3000)
        button.click()
        guard.stop()

    name_dialog(panel.rename_button, "Opening")
    assert c.current_playlist.name == panel.selector.currentText() == "Opening"
    c.set_items([root / "still.png", root / "once.gif"])
    panel.seconds.setValue(1.5)
    panel.repeat.setChecked(True)
    name_dialog(panel.new_button, "Interval")
    assert len(c.playlists) == 2 and c.selected_playlist == 1 and not c.paths
    assert panel.seconds.value() == 5.0 and not panel.repeat.isChecked()
    c.set_items([root / "sample.mp4", root / "missing.mp4"])
    panel.seconds.setValue(2.0)
    name_dialog(panel.rename_button, "Halftime — Interval")
    assert c.current_playlist.name == panel.selector.currentText() == "Halftime — Interval"
    for name in ("", " opening "):
        try:
            c.add_playlist(name)
        except ValueError:
            pass
        else:
            raise AssertionError("Blank or duplicate playlist name accepted")
    panel.selector.setCurrentIndex(0)
    assert [path.name for path in c.paths] == ["still.png", "once.gif"]
    assert panel.seconds.value() == 1.5 and panel.repeat.isChecked()
    c.start()
    c.pause()
    assert not panel.selector.isEnabled() and not panel.new_button.isEnabled()
    assert not c.select_playlist(1) and c.selected_playlist == 0
    name_dialog(panel.rename_button, "Opening set")
    assert c.active and c.paused and c.current_playlist.name == "Opening set"
    c.stop()
    assert panel.selector.isEnabled() and panel.new_button.isEnabled()
    panel.selector.setCurrentIndex(1)
    assert panel.seconds.value() == 2.0 and not panel.repeat.isChecked()
    assert [path.name for path in c.paths] == ["sample.mp4", "missing.mp4"]
    checks.append("Add/rename dialogs, unique names, independent playlist contents and timing, and safe selection during playback")

    session = root / "Multiple.imagedesk.json"
    window.save_session_file(session)
    data = json.loads(session.read_text(encoding="utf-8"))
    assert data["version"] == 2 and data["selected_playlist"] == 1
    assert [entry["name"] for entry in data["playlists"]] == ["Opening set", "Halftime — Interval"], data["playlists"]
    assert data["playlists"][0]["items"] == ["still.png", "once.gif"]
    assert data["playlists"][1]["items"] == ["sample.mp4", "missing.mp4"]
    assert data["settings"]["alignment"] == "Center"
    moved = root / "moved-playlists"
    moved.mkdir()
    for name in ("still.png", "once.gif", "sample.mp4", session.name):
        shutil.copy2(root / name, moved / name)
    c.rename_playlist("Temporary")
    c.set_items([])
    window.alignment_combo.setCurrentIndex(0)
    assert window.open_session_file(moved / session.name, quiet=True)
    assert [entry.name for entry in c.playlists] == ["Opening set", "Halftime — Interval"]
    assert c.selected_playlist == 1 and panel.selector.currentIndex() == 1
    assert window.preview.alignment == "Center" and not c.active and window.current_path is None
    assert all(path.parent == moved for entry in c.playlists for path in entry.paths)
    assert "missing" in panel.list.item(1).text()
    panel.selector.setCurrentIndex(0)
    assert panel.seconds.value() == 1.5 and panel.repeat.isChecked()
    panel.selector.setCurrentIndex(1)
    assert panel.seconds.value() == 2.0 and not panel.repeat.isChecked()
    before = c.export_playlists()
    bad = root / "bad-collection.imagedesk.json"
    for change in ("duplicate", "selection", "alignment"):
        damaged = json.loads(json.dumps(data))
        if change == "duplicate":
            damaged["playlists"][1]["name"] = damaged["playlists"][0]["name"]
        elif change == "selection":
            damaged["selected_playlist"] = 50
        else:
            damaged["settings"]["alignment"] = "Invalid"
        bad.write_text(json.dumps(damaged))
        assert not window.open_session_file(bad, quiet=True)
        assert c.export_playlists() == before and c.selected_playlist == 1
    checks.append("Portable multi-playlist sessions preserve names, order, selected playlist and alignment; invalid collections leave the show intact")

    legacy = root / "Legacy.imagedesk.json"
    legacy.write_text(json.dumps({"format": "image-desk-session", "version": 1,
                                 "items": ["still.png", "once.gif"],
                                 "settings": {"still_seconds": 4.0, "repeat_playlist": True}}))
    assert window.open_session_file(legacy, quiet=True)
    assert len(c.playlists) == 1 and c.current_playlist.name == "Playlist 1"
    assert [path.name for path in c.paths] == ["still.png", "once.gif"]
    assert panel.seconds.value() == 4.0 and panel.repeat.isChecked()
    assert window.preview.alignment == "Top left" and not c.active
    window.save_session_file(root / "Legacy-upgraded.imagedesk.json")
    assert json.loads((root / "Legacy-upgraded.imagedesk.json").read_text(encoding="utf-8"))["version"] == 2
    checks.append("Existing single-playlist sessions load and upgrade without losing media order or timing")
