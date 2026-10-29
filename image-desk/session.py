"""Portable playlist session files. Media stays in its original location."""

import json
import math
import os
import tempfile
from pathlib import Path

if __package__:
    from .playlist_data import PlaylistData, validate_playlists
else:
    from playlist_data import PlaylistData, validate_playlists


DEFAULTS = {"still_seconds": 5.0, "repeat_playlist": False, "clip_loop": False,
            "sizing": "Fit", "alignment": "Top left", "show_countdown": False, "volume": 80, "muted": False}


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Session settings must be an object.")
    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in settings:
            continue
        value = settings[key]
        if key in ("repeat_playlist", "clip_loop", "show_countdown", "muted"):
            valid = type(value) is bool
        elif key == "still_seconds":
            valid = type(value) in (int, float) and math.isfinite(value) and 0.5 <= value <= 3600
        elif key == "volume":
            valid = type(value) is int and 0 <= value <= 100
        elif key == "alignment":
            valid = value in ("Top left", "Center")
        else:
            valid = value in ("Fit", "Fill", "Actual size")
        if not valid:
            raise ValueError(f"Invalid session setting: {key}")
        result[key] = value
    return result


def _read_items(items, directory):
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError("The session must contain a playlist of up to 10,000 items.")
    paths = []
    for item in items:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise ValueError("The session contains an invalid media path.")
        media = Path(item)
        paths.append((media if media.is_absolute() else directory / media).resolve())
    return paths


def read_session(path):
    path = Path(path).resolve()
    if path.stat().st_size > 10_000_000:
        raise ValueError("This session file is too large.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("This is not a valid Image Desk session.") from error
    if (not isinstance(data, dict) or data.get("format") != "image-desk-session"
            or type(data.get("version")) is not int or data["version"] not in (1, 2, 3)):
        raise ValueError("Unsupported Image Desk session format.")
    settings = validate_settings(data.get("settings", {}))
    if data["version"] == 1:
        # Preserve existing single-playlist sessions from Image Desk 3.0/3.0.1.
        playlists = [PlaylistData("Playlist 1", _read_items(data.get("items"), path.parent),
                                  settings["still_seconds"], settings["repeat_playlist"])]
        selected = 0
    else:
        entries = data.get("playlists")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
            raise ValueError("A session must contain between 1 and 100 playlists.")
        playlists = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("The session contains an invalid playlist.")
            playlists.append(PlaylistData(entry.get("name"), _read_items(entry.get("items"), path.parent),
                                          entry.get("still_seconds", 5.0), entry.get("repeat", False),
                                          entry.get("volumes", [])))
        selected = data.get("selected_playlist", 0)
    validate_playlists(playlists, selected)
    settings["still_seconds"] = playlists[selected].still_seconds
    settings["repeat_playlist"] = playlists[selected].repeat
    return playlists, selected, settings


def _write_items(paths, directory):
    items = []
    for media in paths:
        try:
            relative = os.path.relpath(Path(media).resolve(), directory)
            items.append(Path(relative).as_posix())
        except ValueError:  # Windows media on another drive.
            items.append(str(Path(media).resolve()))
    return items


def write_session(path, playlists, selected, settings):
    path = Path(path).resolve()
    validate_playlists(playlists, selected)
    settings = validate_settings(settings)
    # Timing and sequence repeat belong to each playlist, not to the whole show.
    settings.pop("still_seconds")
    settings.pop("repeat_playlist")
    entries = []
    for entry in playlists:
        validated = PlaylistData(entry.name, entry.paths.copy(), entry.still_seconds, entry.repeat,
                                 entry.volumes.copy())
        entries.append({"name": validated.name, "items": _write_items(validated.paths, path.parent),
                        "still_seconds": validated.still_seconds, "repeat": validated.repeat,
                        "volumes": validated.volumes})
    data = {"format": "image-desk-session", "version": 3, "playlists": entries,
            "selected_playlist": selected, "settings": settings}
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if len(payload.encode("utf-8")) > 10_000_000:
        raise ValueError("This session file is too large.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".imagedesk-", suffix=".tmp", delete=False) as file:
            temporary = file.name
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
