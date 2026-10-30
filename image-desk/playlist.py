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
    volumeChanged = Signal(int, int)

    def __init__(self, playback, loader, parent=None):
        super().__init__(parent)
        self.playback, self.loader = playback, loader
        self.playlists = [PlaylistData("Playlist 1")]
        self.selected_playlist = 0
        self.playing_playlist = None
        self.detached = False
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
    def playback_playlist(self):
        return self.playing_playlist or self.current_playlist

    @property
    def playing_paths(self):
        return self.playback_playlist.paths

    @property
    def selected_is_playing(self):
        return self.current_playlist is self.playing_playlist

    @property
    def repeat(self):
        return self.current_playlist.repeat

    @repeat.setter
    def repeat(self, value):
        self.current_playlist.repeat = value
        self.changed.emit()

    @property
    def still_seconds(self):
        return self.current_playlist.still_seconds

    @still_seconds.setter
    def still_seconds(self, value):
        self.current_playlist.still_seconds = value
        self.changed.emit()

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
        if len(self.playlists) >= 100:
            raise ValueError("A session can contain up to 100 playlists.")
        entry = PlaylistData(self._name(name))
        self.playlists.append(entry)
        self.select_playlist(len(self.playlists) - 1)

    def rename_playlist(self, name):
        self.current_playlist.name = self._name(name, self.selected_playlist)
        self.playlistsChanged.emit()
        self.changed.emit()

    def select_playlist(self, selected):
        if not 0 <= selected < len(self.playlists):
            return False
        if selected == self.selected_playlist:
            return True
        self.selected_playlist = selected
        self.playlistsChanged.emit()
        self.itemsChanged.emit()
        self.changed.emit()
        return True

    def _reset_selection(self):
        self.cancel_transition()
        self._bad.clear()
        self.index = -1
        self.playing_playlist = None
        self.detached = False
        self._elapsed = 0.0
        self.status = "Ready"
        self.playlistsChanged.emit()
        self.itemsChanged.emit()
        self.changed.emit()

    def export_playlists(self):
        return [replace(entry, paths=entry.paths.copy(), volumes=entry.volumes.copy()) for entry in self.playlists]

    def replace_playlists(self, entries, selected=0):
        copied = [replace(entry, paths=entry.paths.copy(), volumes=entry.volumes.copy()) for entry in entries]
        validate_playlists(copied, selected)
        self.stop()
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
        return max(0, int(self.playback_playlist.still_seconds * 1000 - elapsed * 1000))

    def set_items(self, paths, volumes=None):
        if self.selected_is_playing:
            self.stop(pause=False)
            self.playing_playlist = None
            self.index = -1
            self.detached = False
        self.paths = [Path(path).expanduser().resolve() for path in paths]
        self.current_playlist.volumes = list(volumes) if volumes is not None else [100] * len(self.paths)
        if not self.active and self.playing_playlist is None:
            self.index = -1
            self._bad.clear()
            self.status = "Ready"
        self.itemsChanged.emit()
        self.changed.emit()

    def add(self, paths):
        paths = [Path(path).expanduser().resolve() for path in paths]
        self.paths.extend(paths)
        self.current_playlist.volumes.extend([100] * len(paths))
        self.itemsChanged.emit()
        self.changed.emit()

    def remove(self, rows):
        excluded = set(rows)
        kept = [i for i in range(len(self.paths)) if i not in excluded]
        mapping = {old: new for new, old in enumerate(kept)}
        if self.selected_is_playing:
            if self.detached or self.index not in mapping:
                # Let the removed on-air item finish; its successor is the
                # first retained row after it, even with duplicate file paths.
                self.index = sum(i <= self.index for i in kept) - 1
                self.detached = True
            else:
                self.index = mapping[self.index]
            self._bad = {mapping[i] for i in self._bad if i in mapping}
        self.paths = [self.paths[i] for i in kept]
        self.current_playlist.volumes = [self.current_playlist.volumes[i] for i in kept]
        self.itemsChanged.emit()
        self.changed.emit()

    def move(self, row, direction):
        target = row + direction
        if not (0 <= row < len(self.paths) and 0 <= target < len(self.paths)):
            return row
        paths = self.paths.copy()
        volumes = self.current_playlist.volumes.copy()
        paths[row], paths[target] = paths[target], paths[row]
        volumes[row], volumes[target] = volumes[target], volumes[row]
        if self.selected_is_playing:
            def moved(i):
                return target if i == row else row if i == target else i
            self.index = moved(self.index + 1) - 1 if self.detached else moved(self.index)
            self._bad = {moved(i) for i in self._bad}
        self.paths, self.current_playlist.volumes = paths, volumes
        self.itemsChanged.emit()
        self.changed.emit()
        return target

    def set_item_volume(self, row, value):
        if not 0 <= row < len(self.paths) or type(value) is not int or not 0 <= value <= 200:
            return
        self.current_playlist.volumes[row] = value
        if self.selected_is_playing and not self.detached and row == self.index:
            self.playback.set_item_volume(value / 100)
        self.volumeChanged.emit(row, value)

    def start(self, index=0, source=None):
        source = source or self.current_playlist
        if not source.paths:
            return
        if not self.active:
            self._saved_loop = self.playback.loop
        self.playing_playlist = source
        self.active, self.paused = True, False
        self.status = "Playing"
        self._bad.clear()
        # Sequence each clip once, independently of the standalone clip mode.
        self._loading = True
        self.playback.set_loop(False)
        self._loading = False
        self.timer.start()
        self._load(max(0, min(index, len(self.playing_paths) - 1)))

    def set_clip_loop(self, loop):
        self._saved_loop = bool(loop)
        self.cancel_transition()
        self.playback.set_loop(bool(loop))
        if self.active and self.playback.ended:
            if loop:
                self.playback.seek(0)
                if not self.paused:
                    self.playback.play()
            elif not self.paused:
                self._queue_advance(False)
        self.changed.emit()

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
            if self.detached:
                self.cancel_transition()
                self._elapsed = 0.0
                self._started = monotonic()
                self.playback.restart()
                self.changed.emit()
            else:
                self._load(self.index)

    def cancel_transition(self):
        self._generation += 1
        self._pending = False

    def step(self, direction):
        if not self.active:
            return
        if not self.playing_paths:
            self.stop(status="Finished")
            return
        target = self.index + direction
        if self.playback_playlist.repeat:
            target %= len(self.playing_paths)
        elif target >= len(self.playing_paths):
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
        self.detached = False
        self._elapsed = 0.0
        self._loading = True
        try:
            self.playback.set_item_volume(self.playback_playlist.volumes[index] / 100)
            ok = self.loader(self.playing_paths[index])
        finally:
            self._loading = False
        self._started = monotonic()
        self.changed.emit()
        if not ok:
            self.notice.emit(f"Skipped unavailable media: {self.playing_paths[index].name}")
            self._queue_advance(True)

    def _media_changed(self):
        if self.active and not self.paused and not self._loading and self.playback.ended and not self.playback.loop:
            self._queue_advance(False)

    def _media_failed(self, message):
        if self.active and not self._loading:
            self.notice.emit(f"Skipped current item: {message}")
            self._queue_advance(True)

    def _tick(self):
        if self.active and not self.paused and not self._loading and self.timed_still:
            if self.still_remaining == 0:
                self._queue_advance(False)

    def _queue_advance(self, failed):
        if not self.active:
            return
        if failed and not self.detached:
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
            if not self.playing_paths:
                self.stop(status="Finished")
                return
            if len(self._bad) == len(self.playing_paths):
                self.stop(status="No playable items")
                self.notice.emit("Playlist stopped: all items are missing or unreadable.")
                return
            target = self.index + 1
            for _ in self.playing_paths:
                if target >= len(self.playing_paths):
                    if not self.playback_playlist.repeat:
                        self.stop(status="Finished")
                        return
                    target = 0
                if target not in self._bad:
                    self._load(target)
                    return
                target += 1

        QTimer.singleShot(0, advance)
