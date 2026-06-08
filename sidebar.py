"""A collapsible navigation sidebar: page thumbnails and document outline.

The sidebar is driven by the currently-active DocumentTab. It shows two tabs:
- Thumbnails: a clickable preview of every page.
- Outline: the PDF's table of contents (bookmarks), if it has one.

Clicking either navigates the active document to the chosen page.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
)

THUMB_PX = 150


class Sidebar(QTabWidget):
    """Thumbnail + outline navigation for the active document."""

    # Emitted with a 0-based page index when the user picks a page.
    page_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(320)

        self._thumbs = QListWidget(self)
        self._thumbs.setIconSize(QSize(THUMB_PX, THUMB_PX))
        self._thumbs.setSpacing(4)
        self._thumbs.setUniformItemSizes(False)
        self._thumbs.itemClicked.connect(self._on_thumb_clicked)
        self.addTab(self._thumbs, "Pages")

        self._outline = QTreeWidget(self)
        self._outline.setHeaderHidden(True)
        self._outline.itemClicked.connect(self._on_outline_clicked)
        self.addTab(self._outline, "Outline")

    def clear(self) -> None:
        self._thumbs.clear()
        self._outline.clear()

    def load_document(self, doc) -> None:
        """Populate thumbnails and the outline from a PdfDocument."""
        self.clear()
        if doc is None or not doc.is_open:
            return

        for i in range(doc.page_count):
            image = doc.render_thumbnail(i, THUMB_PX)
            icon = QIcon(QPixmap.fromImage(image))
            item = QListWidgetItem(icon, f"{i + 1}")
            item.setData(Qt.UserRole, i)
            item.setTextAlignment(Qt.AlignHCenter)
            self._thumbs.addItem(item)

        rows = doc.outline()
        if rows:
            self.setTabEnabled(1, True)
            stack: list[tuple[int, QTreeWidgetItem]] = []
            for level, title, page_index in rows:
                node = QTreeWidgetItem([title])
                node.setData(0, Qt.UserRole, page_index)
                # Find the right parent by walking back to a shallower level.
                while stack and stack[-1][0] >= level:
                    stack.pop()
                if stack:
                    stack[-1][1].addChild(node)
                else:
                    self._outline.addTopLevelItem(node)
                stack.append((level, node))
            self._outline.expandAll()
        else:
            # No bookmarks: keep the tab but show nothing, and default to Pages.
            self.setCurrentIndex(0)

    def highlight_page(self, index: int) -> None:
        """Reflect the current page in the thumbnail list without re-navigating."""
        if 0 <= index < self._thumbs.count():
            self._thumbs.blockSignals(True)
            self._thumbs.setCurrentRow(index)
            self._thumbs.blockSignals(False)

    def _on_thumb_clicked(self, item: QListWidgetItem) -> None:
        self.page_selected.emit(int(item.data(Qt.UserRole)))

    def _on_outline_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if data is not None:
            self.page_selected.emit(int(data))
