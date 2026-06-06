"""A single open PDF shown in one tab: rendering, navigation, zoom, signing."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
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
        # Page layout is computed cheaply from page sizes; pixmaps are rendered
        # lazily for the pages near the viewport (see _render_visible) so large
        # documents don't rasterise every page up front.
        self._page_sizes: list[tuple[float, float]] = []  # logical (w, h) at zoom
        self._page_pos: list[tuple[float, float]] = []  # scene top-left per page
        self._page_bgs: list[QGraphicsRectItem] = []  # white page backgrounds
        self._page_pix: dict[int, QGraphicsPixmapItem] = {}  # rendered pages
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
        """Lay out every page stacked vertically; render the visible ones lazily."""
        if not self.doc.is_open:
            return

        v_bar = self.view.verticalScrollBar()
        h_bar = self.view.horizontalScrollBar()
        v_ratio = (v_bar.value() / v_bar.maximum()) if v_bar.maximum() else 0.0
        h_ratio = (h_bar.value() / h_bar.maximum()) if h_bar.maximum() else 0.0

        # Detach the signature before clearing so Qt doesn't delete the C++ object
        # out from under us; we re-add the same item afterwards.
        keep_sig = self._signature
        if keep_sig is not None:
            self.scene.removeItem(keep_sig)
        self.scene.clear()
        self._page_sizes = []
        self._page_pos = []
        self._page_bgs = []
        self._page_pix = {}
        self._signature = None

        self._dpr = self.view.devicePixelRatioF() or 1.0
        sizes = [
            (w * self.zoom, h * self.zoom)
            for w, h in (self.doc.page_size_points(i) for i in range(self.doc.page_count))
        ]

        # Stack pages top-to-bottom, each centred horizontally on the widest page.
        max_width = max((w for w, _ in sizes), default=0.0)
        page_pen = QPen(QColor(0, 0, 0, 0))  # invisible border (no Qt.NoPen enum)
        page_brush = QBrush(QColor(255, 255, 255))
        y = 0.0
        for w, h in sizes:
            x = (max_width - w) / 2.0
            bg = self.scene.addRect(QRectF(0.0, 0.0, w, h), page_pen, page_brush)
            bg.setPos(x, y)
            bg.setZValue(0)
            self._page_bgs.append(bg)
            self._page_sizes.append((w, h))
            self._page_pos.append((x, y))
            y += h + PAGE_GAP
        total_height = max(0.0, y - PAGE_GAP)
        self.scene.setSceneRect(QRectF(0.0, 0.0, max_width, total_height))

        if keep_sig is not None:
            self.scene.addItem(keep_sig)
            self._signature = keep_sig

        if preserve_scroll:
            v_bar.setValue(int(v_ratio * v_bar.maximum()))
            h_bar.setValue(int(h_ratio * h_bar.maximum()))

        self._render_visible()
        self._update_current_page()
        self.changed.emit()

    def _render_page_item(self, index: int) -> None:
        """Rasterise page ``index`` and place it over its background."""
        pixmap = self.doc.render_page(index, self.zoom, self._dpr)
        item = self.scene.addPixmap(pixmap)
        x, y = self._page_pos[index]
        item.setPos(x, y)
        item.setZValue(1)
        self._page_pix[index] = item

    def _render_visible(self) -> None:
        """Render pages near the viewport and drop pixmaps for pages far from it."""
        if not self._page_sizes:
            return
        height = self.view.viewport().height()
        if height <= 0:
            # Viewport not realised yet (e.g. first layout): render the first page
            # so there's something to show; scrolling will fill in the rest.
            band_top, band_bottom = 0.0, self._page_sizes[0][1]
        else:
            top = float(self.view.verticalScrollBar().value())
            band_top = top - height
            band_bottom = top + 2.0 * height
        for i in range(len(self._page_sizes)):
            rect = self._page_rect_in_scene(i)
            visible = rect.bottom() >= band_top and rect.top() <= band_bottom
            if visible and i not in self._page_pix:
                self._render_page_item(i)
            elif not visible and i in self._page_pix:
                # Keep a one-screen margin cached; discard anything further out.
                far = (
                    rect.bottom() < band_top - height
                    or rect.top() > band_bottom + height
                )
                if far:
                    self.scene.removeItem(self._page_pix.pop(i))

    def _page_rect_in_scene(self, index: int) -> QRectF:
        """Bounding rect of page ``index`` in scene coordinates."""
        x, y = self._page_pos[index]
        w, h = self._page_sizes[index]
        return QRectF(x, y, w, h)

    def _on_scroll(self, _value: int = 0) -> None:
        self._render_visible()
        if self._update_current_page():
            self.changed.emit()

    def _update_current_page(self) -> bool:
        """Point _current_page at the page nearest the viewport centre."""
        if not self._page_sizes:
            return False
        centre_y = (
            self.view.verticalScrollBar().value()
            + self.view.viewport().height() / 2.0
        )
        new_index = 0
        for i in range(len(self._page_sizes)):
            if self._page_rect_in_scene(i).top() <= centre_y:
                new_index = i
            else:
                break
        if new_index != self._current_page:
            self._current_page = new_index
            return True
        return False

    def _scroll_to_page(self, index: int) -> None:
        if 0 <= index < len(self._page_sizes):
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
        if not self._page_sizes:
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
        if not self.doc.is_open or self._signature is None or not self._page_sizes:
            return False
        sig_rect = self._signature.content_scene_rect()
        page_index = self._page_for_rect(sig_rect)
        if page_index < 0:
            QMessageBox.warning(
                self,
                "Signature off the page",
                "The signature isn't on a page. Drag it onto the page before saving.",
            )
            return False
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
        """Index of the page the rect overlaps most (by area), or -1 if off-page."""
        best_i = -1
        best_area = 0.0
        for i in range(len(self._page_sizes)):
            inter = self._page_rect_in_scene(i).intersected(rect)
            area = inter.width() * inter.height() if not inter.isEmpty() else 0.0
            if area > best_area:
                best_area = area
                best_i = i
        return best_i

    def close_document(self) -> None:
        self.doc.close()
