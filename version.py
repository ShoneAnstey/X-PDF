"""Version information for XPDF.

``__version__`` is the single human-facing version number, bumped by hand for
releases (semantic versioning). Everything else here resolves the *full* build
identity at runtime:

- In a release built by GitHub Actions, a ``build_info.json`` file is generated
  during the workflow (see ``packaging/stamp_build.py``) and bundled next to the
  executable. It records the git commit, the release tag (if any), and the build
  date, so any binary can be traced back to the exact commit and Actions run.
- In a plain source checkout there is no ``build_info.json``; we fall back to the
  current git commit when available, otherwise mark the build as ``dev``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

__version__ = "0.6.0"


def _base_dir() -> str:
    """Directory to look in for the bundled build_info.json."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _load_build_info() -> dict[str, str]:
    """Read build metadata written by CI, or an empty dict if not present."""
    path = os.path.join(_base_dir(), "build_info.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


def _git_commit() -> str:
    """Short commit hash from a source checkout, or '' when unavailable."""
    if getattr(sys, "frozen", False):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def build_metadata() -> dict[str, str]:
    """Return resolved build metadata: version, commit, date, tag.

    ``commit``/``date``/``tag`` may be empty strings when running from source.
    """
    info = _load_build_info()
    tag = info.get("tag", "")
    version = tag[1:] if tag.startswith("v") else (tag or __version__)
    return {
        "version": version,
        "commit": info.get("commit", "") or _git_commit(),
        "date": info.get("date", ""),
        "tag": tag,
    }


def version_string() -> str:
    """Short version for the window title, e.g. '0.1.0' or '0.1.0-dev'."""
    meta = build_metadata()
    if meta["tag"]:
        return meta["version"]
    return f"{meta['version']}-dev"


def version_line() -> str:
    """One-line version with build identity, e.g. for --version output."""
    meta = build_metadata()
    parts = [f"XPDF {version_string()}"]
    detail = ", ".join(p for p in (meta["commit"], meta["date"]) if p)
    if detail:
        parts.append(f"({detail})")
    return " ".join(parts)
