"""A single open PDF shown in one tab: rendering, navigation, zoom, signing."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
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
PAGE_GAP = 12.0  # scene-pixel gap between stacked pages


class DocumentTab(QWidget):
    """Owns one PdfDocument and its view. Emits ``changed`` when state updates."""

    changed = Signal()

    def __init__(self, path: str) -> None:
        super().__init__()
        self.doc = PdfDocument()
        self.path = path
        self.zoom = 1.5
        self._dpr = 1.0
        self._current_page = 0
        self._page_items: list[QGraphicsPixmapItem] = []
        self._signature: SignatureItem | None = None

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(Qt.darkGray)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Smooth scaling so the rendered page never looks jagged.
        self.view.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
        )
        # Catch Ctrl+wheel on the scrolling viewport for zoom.
        self.view.viewport().installEventFilter(self)
        # Keep the status bar's page number in sync as the user scrolls.
        self.view.verticalScrollBar().valueChanged.connect(self._on_scroll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self.doc.load(path)
        self.render_all_pages()

    # ----- Ctrl+wheel zoom ---------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if (
            obj is self.view.viewport()
            and event.type() == QEvent.Wheel
            and event.modifiers() & Qt.ControlModifier
        ):
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return True  # consume so the view doesn't also scroll
        return super().eventFilter(obj, event)

    # ----- info --------------------------------------------------------------
    @property
    def title(self) -> str:
        return os.path.basename(self.path) if self.path else "Untitled"

    def status_text(self) -> str:
        if self.doc.is_open:
            return (
                f"Page {self._current_page + 1} / {self.doc.page_count}"
                f"    {int(self.zoom * 100)}%"
            )
        return "No document"

    # ----- rendering ---------------------------------------------------------
    def render_all_pages(self, preserve_scroll: bool = False) -> None:
        """Render every page stacked vertically into the scene (continuous scroll)."""
        if not self.doc.is_open:
            return

        v_bar = self.view.verticalScrollBar()
        h_bar = self.view.horizontalScrollBar()
        v_ratio = (v_bar.value() / v_bar.maximum()) if v_bar.maximum() else 0.0
        h_ratio = (h_bar.value() / h_bar.maximum()) if h_bar.maximum() else 0.0

        keep_sig = self._signature
        self.scene.clear()
        self._page_items = []
        self._signature = None

        self._dpr = self.view.devicePixelRatioF() or 1.0
        sizes: list[tuple[float, float]] = []
        for i in range(self.doc.page_count):
            pixmap = self.doc.render_page(i, self.zoom, self._dpr)
            item = self.scene.addPixmap(pixmap)
            item.setZValue(0)
            self._page_items.append(item)
            sizes.append((pixmap.width() / self._dpr, pixmap.height() / self._dpr))

        # Stack pages top-to-bottom, each centred horizontally on the widest page.
        max_width = max((w for w, _ in sizes), default=0.0)
        y = 0.0
        for item, (w, h) in zip(self._page_items, sizes, strict=True):
            item.setPos((max_width - w) / 2.0, y)
            y += h + PAGE_GAP
        total_height = max(0.0, y - PAGE_GAP)
        self.scene.setSceneRect(QRectF(0.0, 0.0, max_width, total_height))

        if keep_sig is not None:
            self.scene.addItem(keep_sig)
            self._signature = keep_sig

        if preserve_scroll:
            v_bar.setValue(int(v_ratio * v_bar.maximum()))
            h_bar.setValue(int(h_ratio * h_bar.maximum()))

        self._update_current_page()
        self.changed.emit()

    def _page_rect_in_scene(self, index: int) -> QRectF:
        """Bounding rect of page ``index`` in scene coordinates."""
        item = self._page_items[index]
        pm = item.pixmap()
        pos = item.pos()
        return QRectF(pos.x(), pos.y(), pm.width() / self._dpr, pm.height() / self._dpr)

    def _on_scroll(self, _value: int = 0) -> None:
        if self._update_current_page():
            self.changed.emit()

    def _update_current_page(self) -> bool:
        """Point _current_page at the page nearest the viewport centre."""
        if not self._page_items:
            return False
        centre_y = (
            self.view.verticalScrollBar().value()
            + self.view.viewport().height() / 2.0
        )
        new_index = 0
        for i in range(len(self._page_items)):
            if self._page_rect_in_scene(i).top() <= centre_y:
                new_index = i
            else:
                break
        if new_index != self._current_page:
            self._current_page = new_index
            return True
        return False

    def _scroll_to_page(self, index: int) -> None:
        if 0 <= index < len(self._page_items):
            top = self._page_rect_in_scene(index).top()
            self.view.verticalScrollBar().setValue(int(top))

    # ----- navigation --------------------------------------------------------
    def _ok_to_discard_signature(self) -> bool:
        """Ask before throwing away a placed-but-unsaved signature."""
        if self._signature is None:
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved signature",
            "You placed a signature but haven't saved it yet. Discard it?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    def next_page(self) -> None:
        if self.doc.is_open and self._current_page < self.doc.page_count - 1:
            self._scroll_to_page(self._current_page + 1)

    def prev_page(self) -> None:
        if self.doc.is_open and self._current_page > 0:
            self._scroll_to_page(self._current_page - 1)

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
        self.render_all_pages(preserve_scroll=True)

    def fit_width(self) -> None:
        if not self.doc.is_open:
            return
        width_points, _ = self.doc.page_size_points(self._current_page)
        viewport_width = self.view.viewport().width() - 24
        if width_points > 0 and viewport_width > 0:
            self._apply_zoom(viewport_width / width_points)

    # ----- signature ---------------------------------------------------------
    def add_signature(self, sig_path: str) -> bool:
        if not self._page_items:
            return False
        if self._signature is not None:
            self.scene.removeItem(self._signature)
            self._signature = None
        try:
            item = SignatureItem(sig_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return False
        # Drop the signature centred on whichever page is currently in view.
        page_rect = self._page_rect_in_scene(self._current_page)
        item.setPos(
            page_rect.center().x() - 110,
            page_rect.center().y() - 40,
        )
        self.scene.addItem(item)
        item.setSelected(True)
        self._signature = item
        self.view.ensureVisible(item.content_scene_rect(), 20, 20)
        return True

    @property
    def has_signature(self) -> bool:
        return self._signature is not None

    def save_signed(self, sig_path: str) -> bool:
        if not self.doc.is_open or self._signature is None or not self._page_items:
            return False
        sig_rect = self._signature.content_scene_rect()
        page_index = self._page_for_rect(sig_rect)
        page_rect = self._page_rect_in_scene(page_index)
        # Map the signature from scene coords to pixels local to its page.
        local = (
            sig_rect.left() - page_rect.left(),
            sig_rect.top() - page_rect.top(),
            sig_rect.right() - page_rect.left(),
            sig_rect.bottom() - page_rect.top(),
        )
        try:
            self.doc.stamp_and_save(page_index, sig_path, local, self.zoom)
        except Exception as exc:  # noqa: BLE001 - report any save failure
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{exc}")
            return False
        self._signature = None
        self.render_all_pages(preserve_scroll=True)
        return True

    def _page_for_rect(self, rect: QRectF) -> int:
        """Index of the page the rect overlaps most (by area); falls back to current."""
        best_i = self._current_page
        best_area = -1.0
        for i in range(len(self._page_items)):
            inter = self._page_rect_in_scene(i).intersected(rect)
            area = inter.width() * inter.height() if not inter.isEmpty() else 0.0
            if area > best_area:
                best_area = area
                best_i = i
        return best_i

    def close_document(self) -> None:
        self.doc.close()
