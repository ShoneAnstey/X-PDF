"""A movable, resizable signature overlay for the QGraphicsScene.

The signature is a transparent PNG shown on top of the rendered page. The user can
drag it to reposition and drag the bottom-right handle to resize (aspect ratio kept).
The item reports its scene rectangle so the viewer can map it to PDF coordinates.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

HANDLE_SIZE = 14.0
MIN_SIZE = 24.0


class SignatureItem(QGraphicsObject):
    """Transparent-PNG overlay with move + corner-resize (proportional)."""

    def __init__(self, image_path: str) -> None:
        super().__init__()
        self._source = QImage(image_path)
        if self._source.isNull():
            raise ValueError(f"Could not load signature image: {image_path}")

        self._aspect = self._source.height() / max(1, self._source.width())
        # Sensible default on-screen size.
        width = 220.0
        self._rect = QRectF(0.0, 0.0, width, width * self._aspect)
        self._pixmap = QPixmap.fromImage(self._source)

        self._resizing = False

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(100)

    # ----- geometry ----------------------------------------------------------
    def boundingRect(self) -> QRectF:
        # Pad for the handle and selection border.
        return self._rect.adjusted(-2, -2, HANDLE_SIZE + 2, HANDLE_SIZE + 2)

    def content_scene_rect(self) -> QRectF:
        """The image rectangle (no handle padding) in scene coordinates."""
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
        painter.drawPixmap(self._rect, self._pixmap, QRectF(self._pixmap.rect()))

        if self.isSelected():
            pen = QPen(QColor(40, 120, 240), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect)

            painter.setPen(QPen(QColor(40, 120, 240), 1))
            painter.setBrush(QColor(40, 120, 240, 180))
            painter.drawRect(self._handle_rect())

    # ----- interaction -------------------------------------------------------
    def hoverMoveEvent(self, event) -> None:
        if self._handle_rect().contains(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.LeftButton
            and self._handle_rect().contains(event.pos())
        ):
            self._resizing = True
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            new_width = max(MIN_SIZE, event.pos().x() - self._rect.left())
            self.prepareGeometryChange()
            self._rect = QRectF(
                self._rect.left(),
                self._rect.top(),
                new_width,
                new_width * self._aspect,
            )
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
