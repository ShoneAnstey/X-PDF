"""A movable, editable text overlay for the QGraphicsScene.

The user can click to edit the text and drag the edges to move it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem


class TextItem(QGraphicsTextItem):
    """Editable, movable text overlay."""

    def __init__(self, text: str = "Type here...") -> None:
        super().__init__(text)

        font = QFont("Helvetica", 16)
        self.setFont(font)
        self.setDefaultTextColor(QColor("black"))

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)

        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setZValue(100)

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            # Draw a subtle border when editing/selected
            pen = QPen(QColor(40, 120, 240), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setSelected(False)
        # Re-enable interaction if they want to click it again
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
