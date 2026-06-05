"""XPC PDF — a simple cross-platform PDF reader with signature stamping.

Entry point: creates the Qt application and shows the main window.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from viewer import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("XPC PDF")
    app.setOrganizationName("XPC")

    window = MainWindow()
    window.show()

    # Allow opening a file passed on the command line (e.g. file association).
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        window.open_path(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
