"""Shared test fixtures.

Qt needs a QGuiApplication before QImage/QPixmap rendering works, and tests run
headless, so force the offscreen platform plugin before Qt is imported.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make the application modules importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PySide6.QtGui import QGuiApplication


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """A single QGuiApplication for the whole test session."""
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
