"""Regression checks for stop, on-air edits and silent next-cue thumbnails."""

import shutil

from qtpy import PYSIDE2
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QApplication, QFileDialog

from playlist_data import PlaylistData


def run_checks(window, root, wait, until, checks):
    p, c, panel = window.playback, window.playlist, window.playlist_panel
    c.stop()
    p.set_loop(False)
    window.load_image(root / "stereo.mp4")
    until(lambda: p.playing and p.position > 150)
    window.stop_button.click()
    until(lambda: not p.playing and p.position < 80)
    wait(200)
    assert p.stopped and p.position < 80 and not c.active
    assert window.playback_label.text() == "Stopped"
    window.play_button.click()
    until(lambda: p.playing and p.position > 150)
    window.load_image(root / "once.gif")
    window.stop_button.click()
    wait(400)
    assert p.stopped and not p.playing and p.position == 0 and not p.timer.isActive()
    c.replace_playlists([PlaylistData("Stop check", [root / "still.png", root / "stereo.mp4"], .5)])
    c.start()
    wait(100)
    panel.stop.click()
    wait(600)
    assert not c.active and c.index == 0 and p.stopped
    assert window.remaining_milliseconds() == 500
    window.play_button.click()
    assert c.active and c.index == 0
    c.stop()
    checks.append("Stop button rewinds video/GIF, silences playback, cancels auto-advance and restarts stopped playlists")

    c.replace_playlists([
        PlaylistData("On air", [root / name for name in ("stereo.mp4", "sample.mp4", "stereo.mp4", "still.png")],
                     2.0, False, [20, 30, 80, 100]),
        PlaylistData("Preparing", [root / "stereo.mp4"], 5.0, True, [60])])
    c.start()
    until(lambda: p.playing and p.position > 100)
    player = p.player
    for widget in (panel.selector, panel.add_button, panel.open_button, panel.new_button,
                   panel.rename_button, panel.repeat, panel.seconds, window.repeat_combo):
        assert widget.isEnabled(), widget
    window.repeat_combo.setCurrentIndex(1)
    assert p.loop and c.active
    window.add_playlist_files([root / "sample.mov"])
    assert c.active and p.player is player and len(c.paths) == 5
    c.move(0, 1)
    assert c.index == 1 and p.player is player and p.item_volume == .2
    c.remove([0])
    assert c.index == 0 and not c.detached and p.player is player
    panel.selector.setCurrentIndex(1)
    assert c.active and c.playback_playlist.name == "On air" and p.player is player
    assert panel.start.text() == "Start playlist"
    panel.list.setCurrentRow(0)
    panel.item_volume.setValue(5)
    panel.seconds.setValue(9)
    assert p.item_volume == .2 and c.playback_playlist.still_seconds == 2.0
    assert window.playlist_remaining_milliseconds()[0] >= 2900
    c.add_playlist("More cues")
    window.add_playlist_files([root / "once.gif"])
    c.rename_playlist("Later")
    assert c.active and p.player is player and c.current_playlist.name == "Later"
    panel.selector.setCurrentIndex(0)
    assert c.current_playlist.volumes == [20, 80, 100, 100]
    c.remove([0])
    assert c.detached and c.index == -1 and p.player is player and p.item_volume == .2
    window.repeat_combo.setCurrentIndex(0)
    p.seek(p.duration - 150)
    until(lambda: p.player is not player and c.index == 0 and p.playing)
    assert not c.detached and p.item_volume == .8
    checks.append("Live add/move/remove preserves playback and duplicate-entry gain; other playlists stay editable without taking over output")

    # Loop takes effect during an active sequence, then once resumes advancing.
    window.repeat_combo.setCurrentIndex(1)
    p.seek(p.duration - 180)
    until(lambda: p.position < 500)
    assert c.active and c.index == 0 and p.loop
    assert "repeats" in window.next_preview.detail.text()
    window.repeat_combo.setCurrentIndex(0)
    p.seek(p.duration - 150)
    until(lambda: c.index == 1)
    assert window.current_path == root / "still.png"
    # Removing the remaining rows must finish, not divide by zero or spin.
    panel.repeat.setChecked(True)
    c.remove(list(range(len(c.paths))))
    until(lambda: not c.active)
    assert c.status == "Finished" and not c.paths
    checks.append("Play once/Loop can change live; once resumes sequence, and removing all live rows terminates safely")

    next_video = root / "next clip.mov"
    shutil.copy2(root / "sample.mov", next_video)
    c.replace_playlists([PlaylistData("Thumbnail", [root / "stereo.mp4", next_video, root / "still.png"], 2.0)])
    c.start()
    until(lambda: p.playing)
    player = p.player
    thumb = window.next_preview
    until(lambda: thumb.path == next_video and not thumb.thumbnail.isNull())
    until(lambda: thumb.decoder is None)
    assert p.player is player and c.index == 0 and p.playing
    assert thumb.thumbnail.width() <= 288 and thumb.thumbnail.height() <= 162
    assert thumb.thumbnail.pixelColor(0, 0).name() != "#000000"
    window.pause_current()
    until(lambda: not p.playing)
    # Reorder changes the actual upcoming cue; late frames cannot replace it.
    c.move(2, -1)
    until(lambda: thumb.path == root / "still.png" and not thumb.thumbnail.isNull())
    assert thumb.thumbnail.pixelColor(0, 0).name() == "#123456"
    wait(200)
    assert thumb.path == root / "still.png" and p.player is player and c.paused
    c.step(1)
    until(lambda: thumb.path == next_video and not thumb.thumbnail.isNull())
    c.step(1)
    assert thumb.path is None and thumb.name.text() == "End of playlist"
    panel.repeat.setChecked(True)
    until(lambda: thumb.path == root / "stereo.mp4" and not thumb.thumbnail.isNull())
    c.stop()
    checks.append("Next-cue video thumbnail decodes independently, follows live reordering/repeat/end, and rejects stale frames")

    # Inspect the actual thumbnail decoder's audio route while a fresh request runs.
    other = root / "silent thumbnail.mp4"
    shutil.copy2(root / "stereo.mp4", other)
    thumb.set_item(other, "Silent probe")
    thumb.debounce.stop()
    thumb._load()
    decoder = thumb.decoder
    assert decoder is not None
    if PYSIDE2:
        assert decoder.thumbnail and decoder.audio_bridge is None and decoder.audio.isMuted()
    else:
        assert decoder.audioOutput() is None and decoder.audioBufferOutput() is None
    until(lambda: not thumb.thumbnail.isNull() and thumb.decoder is None)
    c.add_playlist("Prepared live")
    window.add_playlist_files([root / "stereo.mp4"])
    c.select_playlist(0)
    c.start()
    until(lambda: p.playing)
    c.select_playlist(1)
    panel.start.click()
    until(lambda: p.playing and p.position >= 100 and c.playback_playlist.name == "Prepared live")
    player, position = p.player, p.position
    dialog_observed = []

    def cancel_dialog():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QFileDialog) and p.playing and p.position > position:
            dialog_observed.append(True)
            dialog.reject()

    # Dialog construction can process events before the modal window becomes
    # visible on a cold 32-bit Windows runner. Observe the real dialog instead
    # of assuming it is already open at one fixed 400 ms checkpoint.
    monitor = QTimer()
    monitor.setInterval(40)
    monitor.timeout.connect(cancel_dialog)
    monitor.start()
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: QApplication.activeModalWidget().reject()
                          if QApplication.activeModalWidget() else None)
    guard.start(2000)
    panel.add_button.click()
    guard.stop()
    monitor.stop()
    assert dialog_observed == [True] and p.player is player and c.active, (
        dialog_observed, position, p.position, p.playing, p.player is player, c.active)
    # An explicit session replacement remains usable while a show is running.
    session = root / "Live-session.imagedesk.json"
    window.save_session_file(session)
    c.start()
    until(lambda: p.playing)
    assert panel.open_button.isEnabled() and window.open_session_file(session, quiet=True)
    assert not c.active and p.player is None and window.current_path is None
    checks.append("Thumbnail has no audio output; prepared playlist starts live; file dialog keeps playback running; session opens during playback")
