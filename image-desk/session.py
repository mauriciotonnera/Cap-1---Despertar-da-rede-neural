"""Portable playlist session files. Media stays in its original location."""

import json
import math
import os
import tempfile
from pathlib import Path


DEFAULTS = {"still_seconds": 5.0, "repeat_playlist": False, "clip_loop": False,
            "sizing": "Fit", "show_countdown": False, "volume": 80, "muted": False}


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
        else:
            valid = value in ("Fit", "Fill", "Actual size")
        if not valid:
            raise ValueError(f"Invalid session setting: {key}")
        result[key] = value
    return result


def read_session(path):
    path = Path(path).resolve()
    if path.stat().st_size > 10_000_000:
        raise ValueError("This session file is too large.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("This is not a valid Image Desk session.") from error
    if not isinstance(data, dict) or data.get("format") != "image-desk-session" or data.get("version") != 1:
        raise ValueError("Unsupported Image Desk session format.")
    items = data.get("items")
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError("The session must contain a playlist of up to 10,000 items.")
    paths = []
    for item in items:
        if not isinstance(item, str) or not item or "\x00" in item:
            raise ValueError("The session contains an invalid media path.")
        media = Path(item)
        paths.append((media if media.is_absolute() else path.parent / media).resolve())
    return paths, validate_settings(data.get("settings", {}))


def write_session(path, paths, settings):
    path = Path(path).resolve()
    settings = validate_settings(settings)
    items = []
    for media in paths:
        try:
            relative = os.path.relpath(Path(media).resolve(), path.parent)
            items.append(Path(relative).as_posix())
        except ValueError:  # Windows media on another drive.
            items.append(str(Path(media).resolve()))
    data = {"format": "image-desk-session", "version": 1, "items": items, "settings": settings}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".imagedesk-", suffix=".tmp", delete=False) as file:
            temporary = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
