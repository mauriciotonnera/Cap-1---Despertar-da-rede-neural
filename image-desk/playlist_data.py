"""Named playlist data and validation shared by the player and session files."""

from dataclasses import dataclass, field
import math
from pathlib import Path


def playlist_name(value):
    if not isinstance(value, str):
        raise ValueError("Enter a playlist name.")
    name = " ".join(value.split())
    if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
        raise ValueError("Playlist names must contain 1–80 characters.")
    return name


@dataclass
class PlaylistData:
    name: str
    paths: list = field(default_factory=list)
    still_seconds: float = 5.0
    repeat: bool = False
    volumes: list = field(default_factory=list)

    def __post_init__(self):
        self.name = playlist_name(self.name)
        if not isinstance(self.paths, list) or len(self.paths) > 10000:
            raise ValueError("A playlist can contain up to 10,000 media files.")
        self.paths = [Path(path).expanduser().resolve() for path in self.paths]
        if not isinstance(self.volumes, list):
            raise ValueError("Playlist item volumes must be a list.")
        if not self.volumes:
            self.volumes = [100] * len(self.paths)
        if (not isinstance(self.volumes, list) or len(self.volumes) != len(self.paths)
                or any(type(v) is not int or not 0 <= v <= 100 for v in self.volumes)):
            raise ValueError("Each playlist item needs a volume between 0 and 100 percent.")
        if (type(self.still_seconds) not in (int, float) or not math.isfinite(self.still_seconds)
                or not 0.5 <= self.still_seconds <= 3600):
            raise ValueError("Still-image duration must be between 0.5 and 3,600 seconds.")
        if type(self.repeat) is not bool:
            raise ValueError("Repeat playlist must be true or false.")


def validate_playlists(playlists, selected):
    if not isinstance(playlists, list) or not 1 <= len(playlists) <= 100:
        raise ValueError("A session must contain between 1 and 100 playlists.")
    if type(selected) is not int or not 0 <= selected < len(playlists):
        raise ValueError("The selected playlist is invalid.")
    names = [entry.name.casefold() for entry in playlists]
    if len(names) != len(set(names)):
        raise ValueError("Each playlist needs a different name.")
    if sum(len(entry.paths) for entry in playlists) > 10000:
        raise ValueError("A session can contain up to 10,000 media entries in total.")
