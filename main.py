"""XPDF — a simple cross-platform PDF reader with signature stamping.

Entry point: creates the Qt application and shows the main window.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from version import __version__, version_line
from viewer import MainWindow


def _icon_path() -> str:
    # Works both from source (packaging/icon.png) and from a PyInstaller bundle,
    # where data files are unpacked next to the executable under sys._MEIPASS.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for candidate in (
        os.path.join(base, "icon.png"),
        os.path.join(base, "packaging", "icon.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", "icon.png"),
    ):
        if os.path.exists(candidate):
            return candidate
    return ""


def main() -> int:
    if "--version" in sys.argv[1:] or "-V" in sys.argv[1:]:
        print(version_line())
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("XPDF")
    app.setApplicationDisplayName("XPDF")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("XPC")

    icon = _icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))

    window = MainWindow()
    window.show()

    # Open any PDFs passed on the command line (e.g. file association).
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf") and os.path.exists(arg):
            window.open_path(arg)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
