"""Playlist sequencing, with one clock for timed stills and guarded transitions."""

from pathlib import Path
from time import monotonic
from dataclasses import replace

from qtpy.QtCore import QObject, QTimer, Signal

if __package__:
    from .playlist_data import PlaylistData, playlist_name, validate_playlists
else:
    from playlist_data import PlaylistData, playlist_name, validate_playlists


class Playlist(QObject):
    changed = Signal()
    itemsChanged = Signal()
    playlistsChanged = Signal()
    notice = Signal(str)

    def __init__(self, playback, loader, parent=None):
        super().__init__(parent)
        self.playback, self.loader = playback, loader
        self.playlists = [PlaylistData("Playlist 1")]
        self.selected_playlist = 0
        self.index = -1
        self.active = self.paused = False
        self.status = "Ready"
        self._saved_loop = False
        self._generation = 0
        self._loading = self._pending = False
        self._bad = set()
        self._elapsed = 0.0
        self._started = monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        playback.changed.connect(self._media_changed)
        playback.failed.connect(self._media_failed)

    @property
    def current_playlist(self):
        return self.playlists[self.selected_playlist]

    @property
    def paths(self):
        return self.current_playlist.paths

    @paths.setter
    def paths(self, value):
        self.current_playlist.paths = value

    @property
    def repeat(self):
        return self.current_playlist.repeat

    @repeat.setter
    def repeat(self, value):
        self.current_playlist.repeat = value

    @property
    def still_seconds(self):
        return self.current_playlist.still_seconds

    @still_seconds.setter
    def still_seconds(self, value):
        self.current_playlist.still_seconds = value

    def suggested_name(self):
        names = {entry.name.casefold() for entry in self.playlists}
        number = 1
        while f"playlist {number}" in names:
            number += 1
        return f"Playlist {number}"

    def _name(self, name, exclude=-1):
        name = playlist_name(name)
        if any(i != exclude and entry.name.casefold() == name.casefold()
               for i, entry in enumerate(self.playlists)):
            raise ValueError("A playlist with that name already exists. Choose a different name.")
        return name

    def add_playlist(self, name):
        if self.active:
            raise ValueError("Stop playback before adding a playlist.")
        if len(self.playlists) >= 100:
            raise ValueError("A session can contain up to 100 playlists.")
        entry = PlaylistData(self._name(name))
        self.playlists.append(entry)
        self.select_playlist(len(self.playlists) - 1)

    def rename_playlist(self, name):
        self.current_playlist.name = self._name(name, self.selected_playlist)
        self.playlistsChanged.emit()

    def select_playlist(self, selected):
        if self.active or not 0 <= selected < len(self.playlists):
            return False
        if selected == self.selected_playlist:
            return True
        self.selected_playlist = selected
        self._reset_selection()
        return True

    def _reset_selection(self):
        self.cancel_transition()
        self.index = -1
        self._elapsed = 0.0
        self.status = "Ready"
        self.playlistsChanged.emit()
        self.itemsChanged.emit()
        self.changed.emit()

    def export_playlists(self):
        return [replace(entry, paths=entry.paths.copy()) for entry in self.playlists]

    def replace_playlists(self, entries, selected=0):
        if self.active:
            raise ValueError("Stop playback before opening a session.")
        copied = [replace(entry, paths=entry.paths.copy()) for entry in entries]
        validate_playlists(copied, selected)
        self.playlists, self.selected_playlist = copied, selected
        self._reset_selection()

    @property
    def timed_still(self):
        return self.playback.kind == "image" or (
            self.playback.kind == "gif" and self.playback.frame_count <= 1)

    @property
    def still_remaining(self):
        elapsed = self._elapsed
        if self.active and not self.paused and not self._loading:
            elapsed += monotonic() - self._started
        return max(0, int(self.still_seconds * 1000 - elapsed * 1000))

    def set_items(self, paths):
        if self.active:
            return
        self.paths = [Path(path).expanduser().resolve() for path in paths]
        self.index = -1
        self.status = "Ready"
        self.itemsChanged.emit()
        self.changed.emit()

    def add(self, paths):
        self.set_items(self.paths + list(paths))

    def remove(self, rows):
        excluded = set(rows)
        self.set_items([p for i, p in enumerate(self.paths) if i not in excluded])

    def move(self, row, direction):
        target = row + direction
        if self.active or not (0 <= row < len(self.paths) and 0 <= target < len(self.paths)):
            return row
        paths = self.paths.copy()
        paths[row], paths[target] = paths[target], paths[row]
        self.set_items(paths)
        return target

    def start(self, index=0):
        if not self.paths:
            return
        if not self.active:
            self._saved_loop = self.playback.loop
        self.active, self.paused = True, False
        self.status = "Playing"
        self._bad.clear()
        # Sequence each clip once, independently of the standalone clip mode.
        self._loading = True
        self.playback.set_loop(False)
        self._loading = False
        self.timer.start()
        self._load(max(0, min(index, len(self.paths) - 1)))

    def pause(self):
        if not self.active or self.paused:
            return
        if self.timed_still:
            self._elapsed += monotonic() - self._started
        self.paused = True
        self.status = "Paused"
        self.playback.pause()
        self.changed.emit()

    def resume(self):
        if not self.active or not self.paused:
            return
        self.paused = False
        self.status = "Playing"
        self._started = monotonic()
        if self.playback.error or self.playback.ended:
            self._queue_advance(bool(self.playback.error))
        elif not self.timed_still:
            self.playback.play()
        self.changed.emit()

    def stop(self, pause=True, status="Stopped"):
        was_active = self.active
        if was_active and not self.paused and self.timed_still:
            self._elapsed += monotonic() - self._started
        self.active = self.paused = self._pending = False
        self._generation += 1  # Cancel transitions queued by the previous file.
        self.timer.stop()
        if was_active:
            if pause:
                self.playback.pause()
            self.playback.set_loop(self._saved_loop)
            self.status = status
        self.changed.emit()

    def restart_item(self):
        if self.active:
            self.paused = False
            self.status = "Playing"
            self._load(self.index)

    def cancel_transition(self):
        self._generation += 1
        self._pending = False

    def step(self, direction):
        if not self.active:
            return
        target = self.index + direction
        if self.repeat:
            target %= len(self.paths)
        elif target >= len(self.paths):
            self.stop(status="Finished")
            return
        else:
            target = max(0, target)
        self.paused = False
        self.status = "Playing"
        self._load(target)

    def _load(self, index):
        self._generation += 1
        self._pending = False
        self.index = index
        self._elapsed = 0.0
        self._loading = True
        try:
            ok = self.loader(self.paths[index])
        finally:
            self._loading = False
        self._started = monotonic()
        self.changed.emit()
        if not ok:
            self.notice.emit(f"Skipped unavailable media: {self.paths[index].name}")
            self._queue_advance(True)

    def _media_changed(self):
        if self.active and not self.paused and not self._loading and self.playback.ended:
            self._queue_advance(False)

    def _media_failed(self, message):
        if self.active and not self._loading:
            self.notice.emit(f"Skipped {self.paths[self.index].name}: {message}")
            self._queue_advance(True)

    def _tick(self):
        if self.active and not self.paused and not self._loading and self.timed_still:
            if self.still_remaining == 0:
                self._queue_advance(False)

    def _queue_advance(self, failed):
        if not self.active:
            return
        if failed:
            self._bad.add(self.index)
        if self._pending:
            return
        self._pending = True
        generation = self._generation

        def advance():
            if generation != self._generation:
                return
            self._pending = False
            if not self.active or self.paused:
                return
            if len(self._bad) == len(self.paths):
                self.stop(status="No playable items")
                self.notice.emit("Playlist stopped: all items are missing or unreadable.")
                return
            target = self.index + 1
            for _ in self.paths:
                if target >= len(self.paths):
                    if not self.repeat:
                        self.stop(status="Finished")
                        return
                    target = 0
                if target not in self._bad:
                    self._load(target)
                    return
                target += 1

        QTimer.singleShot(0, advance)
