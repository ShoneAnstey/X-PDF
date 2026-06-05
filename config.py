"""Cross-platform persistent settings via QSettings.

Stores the remembered signature image path, the last-used folder, and basic window
geometry. QSettings writes to the registry on Windows and to an INI/conf file under
~/.config on Linux, so there are no stray files to manage.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

ORG = "XPC"
APP = "XPC PDF"

_SIGNATURE_PATH = "signature/path"
_LAST_DIR = "files/last_dir"
_WINDOW_GEOMETRY = "window/geometry"
_WINDOW_STATE = "window/state"


def _settings() -> QSettings:
    return QSettings(ORG, APP)


def get_signature_path() -> str | None:
    value = _settings().value(_SIGNATURE_PATH)
    return str(value) if value else None


def set_signature_path(path: str) -> None:
    _settings().setValue(_SIGNATURE_PATH, path)


def get_last_dir() -> str | None:
    value = _settings().value(_LAST_DIR)
    return str(value) if value else None


def set_last_dir(path: str) -> None:
    _settings().setValue(_LAST_DIR, path)


def get_window_geometry():
    return _settings().value(_WINDOW_GEOMETRY)


def set_window_geometry(geometry) -> None:
    _settings().setValue(_WINDOW_GEOMETRY, geometry)
