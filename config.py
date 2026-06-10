"""Cross-platform persistent settings via QSettings.

Stores the remembered signature image path, the last-used folder, and basic window
geometry. QSettings writes to the registry on Windows and to an INI/conf file under
~/.config on Linux, so there are no stray files to manage.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QStandardPaths

ORG = "XPC"
APP = "XPDF"

_SIGNATURE_PATH = "signature/path"
_LAST_DIR = "files/last_dir"
_WINDOW_GEOMETRY = "window/geometry"
_WINDOW_STATE = "window/state"
_RECENT_FILES = "files/recent"
_DARK_MODE = "ui/dark_mode"
_SIDEBAR_VISIBLE = "ui/sidebar_visible"


def _settings() -> QSettings:
    return QSettings(ORG, APP)

def get_recent_files() -> list[str]:
    value = _settings().value(_RECENT_FILES, [])
    # QSettings stores string lists, but a single-entry list can come back as a
    # plain string on some backends.
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return []


def set_recent_files(paths: list[str]) -> None:
    _settings().setValue(_RECENT_FILES, list(paths))


def add_recent_file(path: str) -> None:
    recent = get_recent_files()
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    set_recent_files(recent[:10])  # keep top 10


def clear_recent_files() -> None:
    _settings().remove(_RECENT_FILES)


def get_signature_path() -> str | None:
    value = _settings().value(_SIGNATURE_PATH)
    return str(value) if value else None


def set_signature_path(path: str) -> None:
    _settings().setValue(_SIGNATURE_PATH, path)


def clear_signature_path() -> None:
    _settings().remove(_SIGNATURE_PATH)


def get_last_dir() -> str | None:
    value = _settings().value(_LAST_DIR)
    return str(value) if value else None


def set_last_dir(path: str) -> None:
    _settings().setValue(_LAST_DIR, path)


def get_window_geometry():
    return _settings().value(_WINDOW_GEOMETRY)


def set_window_geometry(geometry) -> None:
    _settings().setValue(_WINDOW_GEOMETRY, geometry)


def get_dark_mode() -> bool:
    return bool(_settings().value(_DARK_MODE, False, type=bool))


def set_dark_mode(enabled: bool) -> None:
    _settings().setValue(_DARK_MODE, bool(enabled))


def get_sidebar_visible() -> bool:
    return bool(_settings().value(_SIDEBAR_VISIBLE, True, type=bool))


def set_sidebar_visible(visible: bool) -> None:
    _settings().setValue(_SIDEBAR_VISIBLE, bool(visible))


def cache_dir() -> str:
    """Return a writable per-user cache directory for XPDF, creating it if needed."""
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache", APP)
    os.makedirs(base, exist_ok=True)
    return base

