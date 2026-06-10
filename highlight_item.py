"""A movable, resizable highlight overlay for the QGraphicsScene.

A translucent marker-yellow rectangle the user drags over text. Drag the
bottom-right handle to resize, press Delete/Backspace to remove it. On save it
is written into the PDF as a real highlight annotation.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

HANDLE_SIZE = 12.0
MIN_W = 24.0
MIN_H = 12.0
DEFAULT_W = 220.0
DEFAULT_H = 26.0

FILL = QColor(255, 230, 0, 100)  # translucent marker yellow
BORDER = QColor(40, 120, 240)


class HighlightItem(QGraphicsObject):
    """Translucent yellow rectangle with move + free corner-resize."""

    remove_requested = Signal(object)  # emits self

    def __init__(self) -> None:
        super().__init__()
        self._rect = QRectF(0.0, 0.0, DEFAULT_W, DEFAULT_H)
        self._resizing = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        # Below text/signature overlays (100) but above the rendered page (1).
        self.setZValue(60)

    # ----- geometry ----------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-2, -2, HANDLE_SIZE + 2, HANDLE_SIZE + 2)

    def content_scene_rect(self) -> QRectF:
        """The highlight rectangle (no handle padding) in scene coordinates."""
        return self.mapToScene(self._rect).boundingRect()

    def _handle_rect(self) -> QRectF:
        return QRectF(
            self._rect.right(),
            self._rect.bottom(),
            HANDLE_SIZE,
            HANDLE_SIZE,
        )

    # ----- painting ----------------------------------------------------------
    def paint(
        self,
        painter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FILL)
        painter.drawRect(self._rect)

        if self.isSelected():
            pen = QPen(BORDER, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)

            painter.setPen(QPen(BORDER, 1))
            painter.setBrush(QColor(BORDER.red(), BORDER.green(), BORDER.blue(), 180))
            painter.drawRect(self._handle_rect())

    # ----- interaction -------------------------------------------------------
    def hoverMoveEvent(self, event) -> None:
        if self._handle_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._handle_rect().contains(event.pos())
        ):
            self._resizing = True
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            new_w = max(MIN_W, event.pos().x() - self._rect.left())
            new_h = max(MIN_H, event.pos().y() - self._rect.top())
            self.prepareGeometryChange()
            self._rect = QRectF(self._rect.left(), self._rect.top(), new_w, new_h)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resizing:
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_requested.emit(self)
            event.accept()
            return
        super().keyPressEvent(event)
