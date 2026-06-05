"""A single open PDF shown in one tab: rendering, navigation, zoom, signing."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from pdf_document import PdfDocument
from signature_item import SignatureItem

ZOOM_MIN = 0.25
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25


class DocumentTab(QWidget):
    """Owns one PdfDocument and its view. Emits ``changed`` when state updates."""

    changed = Signal()

    def __init__(self, path: str) -> None:
        super().__init__()
        self.doc = PdfDocument()
        self.path = path
        self.page_index = 0
        self.zoom = 1.5
        self._page_item: QGraphicsPixmapItem | None = None
        self._signature: SignatureItem | None = None

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(Qt.darkGray)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self.doc.load(path)
        self.render_current_page()

    # ----- info --------------------------------------------------------------
    @property
    def title(self) -> str:
        return os.path.basename(self.path) if self.path else "Untitled"

    def status_text(self) -> str:
        if self.doc.is_open:
            return (
                f"Page {self.page_index + 1} / {self.doc.page_count}"
                f"    {int(self.zoom * 100)}%"
            )
        return "No document"

    # ----- rendering ---------------------------------------------------------
    def render_current_page(self) -> None:
        if not self.doc.is_open:
            return
        keep_sig = self._signature
        self.scene.clear()
        self._page_item = None
        self._signature = None

        pixmap = self.doc.render_page(self.page_index, self.zoom)
        self._page_item = self.scene.addPixmap(pixmap)
        self._page_item.setZValue(0)
        self.scene.setSceneRect(self._page_item.boundingRect())

        if keep_sig is not None:
            self.scene.addItem(keep_sig)
            self._signature = keep_sig
        self.changed.emit()

    # ----- navigation --------------------------------------------------------
    def next_page(self) -> None:
        if self.doc.is_open and self.page_index < self.doc.page_count - 1:
            self.page_index += 1
            self._signature = None
            self.render_current_page()

    def prev_page(self) -> None:
        if self.doc.is_open and self.page_index > 0:
            self.page_index -= 1
            self._signature = None
            self.render_current_page()

    # ----- zoom --------------------------------------------------------------
    def zoom_in(self) -> None:
        self._apply_zoom(self.zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(self.zoom / ZOOM_STEP)

    def _apply_zoom(self, value: float) -> None:
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        if abs(value - self.zoom) < 1e-6:
            return
        self.zoom = value
        self.render_current_page()

    def fit_width(self) -> None:
        if not self.doc.is_open:
            return
        width_points, _ = self.doc.page_size_points(self.page_index)
        viewport_width = self.view.viewport().width() - 24
        if width_points > 0 and viewport_width > 0:
            self._apply_zoom(viewport_width / width_points)

    # ----- signature ---------------------------------------------------------
    def add_signature(self, sig_path: str) -> bool:
        if self._signature is not None:
            self.scene.removeItem(self._signature)
            self._signature = None
        try:
            item = SignatureItem(sig_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return False
        page_rect = self._page_item.boundingRect()
        item.setPos(
            page_rect.width() / 2 - 110,
            page_rect.height() / 2 - 40,
        )
        self.scene.addItem(item)
        item.setSelected(True)
        self._signature = item
        return True

    @property
    def has_signature(self) -> bool:
        return self._signature is not None

    def save_signed(self, sig_path: str) -> bool:
        if not self.doc.is_open or self._signature is None:
            return False
        rect = self._signature.content_scene_rect()
        try:
            self.doc.stamp_and_save(
                self.page_index,
                sig_path,
                (rect.left(), rect.top(), rect.right(), rect.bottom()),
                self.zoom,
            )
        except Exception as exc:  # noqa: BLE001 - report any save failure
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{exc}")
            return False
        self._signature = None
        self.render_current_page()
        return True

    def close_document(self) -> None:
        self.doc.close()
