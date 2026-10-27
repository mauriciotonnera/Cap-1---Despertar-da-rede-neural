"""Native integration checks for playlist timing, output controls and sessions."""

import base64
import json
import shutil


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
    data = json.loads(session.read_text())
    assert data["items"] == ["once.gif", "still.png", "missing.mp4"]
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
