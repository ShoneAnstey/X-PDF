"""A single open PDF shown in one tab: rendering, navigation, zoom, signing."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pdf_document import PdfDocument, PdfAnnotation
from signature_item import SignatureItem
from text_item import TextItem

ZOOM_MIN = 0.25
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25
PAGE_GAP = 12.0  # scene-pixel gap between stacked pages
SEARCH_CHUNK_PAGES = 50  # pages searched per event-loop slice (keeps UI responsive)


class DocumentTab(QWidget):
    """Owns one PdfDocument and its view. Emits ``changed`` when state updates."""

    changed = Signal()
    # Emitted when the page set changes (e.g. a page is deleted) so the sidebar
    # can rebuild its thumbnails and outline.
    structure_changed = Signal()

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
        self._texts: list[TextItem] = []

        # Search state: matches are kept in PDF-point coords per page so they
        # survive zoom; overlays are rebuilt from them on every re-render. Pages
        # are searched in chunks on a zero-interval timer so a huge document
        # doesn't freeze the UI.
        self._matches: list[tuple[int, tuple[float, float, float, float]]] = []
        self._match_overlays: list[QGraphicsRectItem] = []
        self._match_index: int = -1
        self._search_text: str = ""
        self._search_cursor: int = 0
        self._search_timer = QTimer(self)
        self._search_timer.setInterval(0)
        self._search_timer.timeout.connect(self._search_chunk)

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
        # Right-click a page for surgery (extract / delete).
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_page_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_find_bar())
        layout.addWidget(self.view)

        self.doc.load(path)
        self.render_all_pages()

    # ----- find bar ----------------------------------------------------------
    def _build_find_bar(self) -> QWidget:
        self.find_bar = QWidget(self)
        self.find_input = QLineEdit(self.find_bar)
        self.find_input.setPlaceholderText("Find in document...")
        self.find_input.returnPressed.connect(self._on_find_enter)

        btn_prev = QPushButton("\u25c0", self.find_bar)
        btn_next = QPushButton("\u25b6", self.find_bar)
        btn_close = QPushButton("\u2715", self.find_bar)
        for btn in (btn_prev, btn_next, btn_close):
            btn.setMaximumWidth(32)
        btn_prev.clicked.connect(self.find_prev)
        btn_next.clicked.connect(self.find_next)
        btn_close.clicked.connect(self.hide_find_bar)

        self.find_status = QLabel("", self.find_bar)
        self.find_status.setMinimumWidth(80)

        row = QHBoxLayout(self.find_bar)
        row.setContentsMargins(6, 2, 6, 2)
        row.addWidget(self.find_input, 1)
        row.addWidget(btn_prev)
        row.addWidget(btn_next)
        row.addWidget(self.find_status)
        row.addWidget(btn_close)

        # Esc inside the find input closes the bar.
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self.find_input)
        esc.activated.connect(self.hide_find_bar)

        self.find_bar.hide()
        return self.find_bar

    def show_find_bar(self) -> None:
        self.find_bar.show()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def hide_find_bar(self) -> None:
        self._clear_matches()
        self._search_text = ""
        self.find_status.clear()
        self.find_bar.hide()
        self.view.setFocus()

    def _on_find_enter(self) -> None:
        text = self.find_input.text().strip()
        if text != self._search_text:
            self._run_search(text)
        else:
            self.find_next()

    def find_next(self) -> None:
        if not self._matches:
            return
        self._set_match_index((self._match_index + 1) % len(self._matches))

    def find_prev(self) -> None:
        if not self._matches:
            return
        self._set_match_index((self._match_index - 1) % len(self._matches))

    def _run_search(self, text: str) -> None:
        self._clear_matches()
        self._search_text = text
        if not text or not self.doc.is_open:
            self.find_status.clear()
            return
        self._search_cursor = 0
        # Run the first chunk synchronously so small documents feel instant;
        # anything left over continues on the timer without blocking the UI.
        self._search_chunk()

    def _search_chunk(self) -> None:
        """Search the next slice of pages; finish or re-arm the timer."""
        if not self.doc.is_open or not self._search_text:
            self._search_timer.stop()
            return
        total = self.doc.page_count
        end = min(self._search_cursor + SEARCH_CHUNK_PAGES, total)
        for i in range(self._search_cursor, end):
            for r in self.doc.search_page(i, self._search_text):
                self._matches.append((i, (r.x0, r.y0, r.x1, r.y1)))
        self._search_cursor = end
        if end < total:
            self.find_status.setText(f"Searching\u2026 {end}/{total}")
            self._search_timer.start()
            return
        self._search_timer.stop()
        if not self._matches:
            self.find_status.setText("No matches")
            return
        self._build_match_overlays()
        self._set_match_index(0)

    def _clear_matches(self) -> None:
        self._search_timer.stop()
        self._search_cursor = 0
        for item in self._match_overlays:
            self.scene.removeItem(item)
        self._match_overlays = []
        self._matches = []
        self._match_index = -1

    def _build_match_overlays(self) -> None:
        """Rebuild highlight rectangles from ``self._matches`` at current zoom."""
        for item in self._match_overlays:
            self.scene.removeItem(item)
        self._match_overlays = []
        if not self._matches or not self._page_pos:
            return
        pen = QPen(QColor(0, 0, 0, 0))
        inactive = QBrush(QColor(255, 235, 59, 110))  # soft yellow
        for page_idx, (x0, y0, x1, y1) in self._matches:
            if page_idx >= len(self._page_pos):
                continue
            px, py = self._page_pos[page_idx]
            rect = QRectF(
                px + x0 * self.zoom,
                py + y0 * self.zoom,
                (x1 - x0) * self.zoom,
                (y1 - y0) * self.zoom,
            )
            item = self.scene.addRect(rect, pen, inactive)
            item.setZValue(50)
            self._match_overlays.append(item)
        if 0 <= self._match_index < len(self._match_overlays):
            self._highlight_active()

    def _highlight_active(self) -> None:
        inactive = QBrush(QColor(255, 235, 59, 110))
        active = QBrush(QColor(255, 140, 0, 200))  # stronger orange
        for i, item in enumerate(self._match_overlays):
            item.setBrush(active if i == self._match_index else inactive)

    def _set_match_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._matches)):
            return
        self._match_index = idx
        self._highlight_active()
        page_idx, (x0, y0, x1, y1) = self._matches[idx]
        px, py = self._page_pos[page_idx]
        rect = QRectF(
            px + x0 * self.zoom,
            py + y0 * self.zoom,
            (x1 - x0) * self.zoom,
            (y1 - y0) * self.zoom,
        )
        self.view.ensureVisible(rect, 40, 40)
        self.find_status.setText(f"{idx + 1} / {len(self._matches)}")

    # ----- Ctrl+wheel zoom ---------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if (
            obj is self.view.viewport()
            and event.type() == QEvent.Wheel
            and event.modifiers() & Qt.ControlModifier
        ):
            anchor = event.position().toPoint()
            if event.angleDelta().y() > 0:
                self.zoom_in(anchor)
            else:
                self.zoom_out(anchor)
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

        # Detach the signature and texts before clearing so Qt doesn't delete the C++ objects
        # out from under us; we re-add the same items afterwards.
        keep_sig = self._signature
        if keep_sig is not None:
            self.scene.removeItem(keep_sig)
        keep_texts = self._texts
        for txt in keep_texts:
            self.scene.removeItem(txt)

        self.scene.clear()
        self._page_sizes = []
        self._page_pos = []
        self._page_bgs = []
        self._page_pix = {}
        # scene.clear() also deleted any search-match overlay C++ objects; the
        # match data in self._matches is preserved and overlays are rebuilt below.
        self._match_overlays = []
        self._signature = None
        self._texts = []

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

        for txt in keep_texts:
            self.scene.addItem(txt)
            self._texts.append(txt)

        if preserve_scroll:
            v_bar.setValue(int(v_ratio * v_bar.maximum()))
            h_bar.setValue(int(h_ratio * h_bar.maximum()))

        self._build_match_overlays()
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
    def ok_to_discard_annotations(self) -> bool:
        """Ask before throwing away any placed-but-unsaved annotations."""
        if self._signature is None and not self._texts:
            return True
        reply = QMessageBox.warning(
            self,
            "Unsaved changes",
            "You placed a signature or text but haven't saved it yet. Discard them?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    def next_page(self) -> None:
        if self.doc.is_open and self._current_page < self.doc.page_count - 1:
            self._scroll_to_page(self._current_page + 1)

    def prev_page(self) -> None:
        if self.doc.is_open and self._current_page > 0:
            self._scroll_to_page(self._current_page - 1)

    @property
    def current_page(self) -> int:
        return self._current_page

    def goto_page(self, index: int) -> None:
        """Public navigation: scroll so page ``index`` is at the top of the view."""
        self._scroll_to_page(index)

    # ----- page surgery ------------------------------------------------------
    def _page_at_viewport_pos(self, view_pos) -> int:
        """Map a position in the view's viewport to a page index, or -1."""
        scene_pos = self.view.mapToScene(view_pos)
        for i in range(len(self._page_sizes)):
            if self._page_rect_in_scene(i).contains(scene_pos):
                return i
        return -1

    def _show_page_menu(self, view_pos) -> None:
        if not self.doc.is_open:
            return
        page_index = self._page_at_viewport_pos(view_pos)
        if page_index < 0:
            page_index = self._current_page

        menu = QMenu(self)
        extract_act = menu.addAction(f"Extract page {page_index + 1} to new PDF...")
        delete_act = menu.addAction(f"Delete page {page_index + 1}")
        # Can't delete the only page.
        delete_act.setEnabled(self.doc.page_count > 1)

        chosen = menu.exec(self.view.viewport().mapToGlobal(view_pos))
        if chosen is extract_act:
            self.extract_page(page_index)
        elif chosen is delete_act:
            self.delete_page(page_index)

    def extract_page(self, page_index: int) -> bool:
        """Save page ``page_index`` as a standalone PDF chosen by the user."""
        if not self.doc.is_open:
            return False
        stem = os.path.splitext(self.title)[0]
        suggested = f"{stem} - page {page_index + 1}.pdf"
        start_dir = os.path.dirname(self.path) if self.path else os.path.expanduser("~")
        target, _ = QFileDialog.getSaveFileName(
            self, "Extract page to PDF", os.path.join(start_dir, suggested),
            "PDF files (*.pdf)",
        )
        if not target:
            return False
        if not target.lower().endswith(".pdf"):
            target += ".pdf"
        try:
            self.doc.extract_pages(target, [page_index])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Extract failed", f"Could not extract page:\n{exc}")
            return False
        return True

    def delete_page(self, page_index: int) -> bool:
        """Delete page ``page_index`` from the document on disk, after confirming."""
        if not self.doc.is_open:
            return False
        if self.doc.page_count <= 1:
            QMessageBox.information(
                self, "Can't delete", "A PDF must keep at least one page."
            )
            return False
        # Deleting rewrites the file, so any placed-but-unsaved signature or text
        # would be lost. Confirm discarding those first (no prompt if there are none).
        if not self.ok_to_discard_annotations():
            return False
        reply = QMessageBox.warning(
            self,
            "Delete page",
            f"Delete page {page_index + 1} of {self.doc.page_count}? "
            "This rewrites the file on disk and can't be undone here.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return False
        try:
            self.doc.delete_page(page_index)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Delete failed", f"Could not delete page:\n{exc}")
            return False
        # The delete succeeded: only now is it safe to drop the unsaved overlays
        # (their page coordinates are no longer valid) and re-render. Search
        # matches also hold pre-delete page indices, so they're invalid too.
        self._discard_overlays()
        self._clear_matches()
        self.find_status.clear()
        self._current_page = min(self._current_page, self.doc.page_count - 1)
        self.render_all_pages()
        self.structure_changed.emit()
        return True

    def _discard_overlays(self) -> None:
        """Remove any placed-but-unsaved signature/text overlays from the scene."""
        if self._signature is not None:
            self.scene.removeItem(self._signature)
            self._signature = None
        for txt in self._texts:
            self.scene.removeItem(txt)
        self._texts = []

    # ----- zoom --------------------------------------------------------------
    def zoom_in(self, anchor: QPoint | None = None) -> None:
        self._apply_zoom(self.zoom * ZOOM_STEP, anchor)

    def zoom_out(self, anchor: QPoint | None = None) -> None:
        self._apply_zoom(self.zoom / ZOOM_STEP, anchor)

    def _apply_zoom(self, value: float, anchor: QPoint | None = None) -> None:
        """Set the zoom level.

        ``anchor`` is an optional viewport position (e.g. the mouse cursor during
        Ctrl+wheel) that should keep pointing at the same spot on the page after
        the zoom; without it the scroll position is preserved proportionally.
        """
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        if abs(value - self.zoom) < 1e-6:
            return

        # Capture the document position under the anchor before re-layout:
        # (page index, offset within the page in PDF points, viewport x/y).
        anchor_state: tuple[int, float, float, float, float] | None = None
        if anchor is not None and self._page_pos:
            scene_pos = self.view.mapToScene(anchor)
            for i in range(len(self._page_sizes)):
                if self._page_rect_in_scene(i).contains(scene_pos):
                    px, py = self._page_pos[i]
                    anchor_state = (
                        i,
                        (scene_pos.x() - px) / self.zoom,
                        (scene_pos.y() - py) / self.zoom,
                        float(anchor.x()),
                        float(anchor.y()),
                    )
                    break

        self.zoom = value
        self.render_all_pages(preserve_scroll=anchor_state is None)

        if anchor_state is not None:
            page, pt_x, pt_y, view_x, view_y = anchor_state
            px, py = self._page_pos[page]
            scene_x = px + pt_x * self.zoom
            scene_y = py + pt_y * self.zoom
            viewport = self.view.viewport()
            self.view.centerOn(
                scene_x + viewport.width() / 2.0 - view_x,
                scene_y + viewport.height() / 2.0 - view_y,
            )
            self._render_visible()

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

    def add_text(self) -> bool:
        """Drop a new editable text item in the centre of the current page."""
        if not self._page_sizes:
            return False

        item = TextItem()
        page_rect = self._page_rect_in_scene(self._current_page)
        item.setPos(
            page_rect.center().x() - item.boundingRect().width() / 2,
            page_rect.center().y() - item.boundingRect().height() / 2,
        )
        self.scene.addItem(item)
        self._texts.append(item)

        # Select and focus so typing immediately goes into the box
        item.setSelected(True)
        item.setFocus()
        self.view.ensureVisible(item.boundingRect(), 20, 20)
        return True

    def rotate_signature(self, delta_deg: int) -> bool:
        """Rotate the placed signature by 90/180/270 degrees. No-op if none placed."""
        if self._signature is None:
            return False
        self._signature.rotate_by(delta_deg)
        # Keep the (now rotated) signature visible in the viewport.
        self.view.ensureVisible(self._signature.content_scene_rect(), 20, 20)
        return True

    @property
    def has_annotations(self) -> bool:
        return self._signature is not None or bool(self._texts)

    def _collect_annotations(self, sig_path: str | None) -> list[PdfAnnotation] | None:
        """Gather all signatures and texts. Returns None if validation fails."""
        annotations = []

        # 1. Signature
        if self._signature is not None:
            if not sig_path:
                QMessageBox.warning(
                    self,
                    "No signature image",
                    "Configure a signature image first via Set Signature.",
                )
                return None
            sig_rect = self._signature.content_scene_rect()
            page_index = self._page_for_rect(sig_rect)
            if page_index < 0:
                QMessageBox.warning(
                    self, "Signature off the page",
                    "The signature isn't on a page. Drag it onto the page before saving.",
                )
                return None
            page_rect = self._page_rect_in_scene(page_index)
            local = (
                sig_rect.left() - page_rect.left(),
                sig_rect.top() - page_rect.top(),
                sig_rect.right() - page_rect.left(),
                sig_rect.bottom() - page_rect.top(),
            )
            annotations.append(PdfAnnotation(
                page_index=page_index,
                rect_pixels=local,
                type="image",
                image_path=sig_path,
                rotation=self._signature.rotation_degrees,
            ))

        # 2. Text items
        for txt in self._texts:
            text_str = txt.toPlainText().strip()
            if not text_str:
                continue  # ignore empty items
            txt_rect = txt.sceneBoundingRect()
            page_index = self._page_for_rect(txt_rect)
            if page_index < 0:
                QMessageBox.warning(
                    self, "Text off the page",
                    f"The text '{text_str[:15]}...' isn't on a page. Drag it onto a page.",
                )
                return None
            page_rect = self._page_rect_in_scene(page_index)
            local = (
                txt_rect.left() - page_rect.left(),
                txt_rect.top() - page_rect.top(),
                txt_rect.right() - page_rect.left(),
                txt_rect.bottom() - page_rect.top(),
            )
            annotations.append(PdfAnnotation(
                page_index=page_index,
                rect_pixels=local,
                type="text",
                text=text_str,
            ))

        return annotations

    def save_signed(self, sig_path: str) -> bool:
        if not self.doc.is_open or not self.has_annotations or not self._page_sizes:
            return False

        annotations = self._collect_annotations(sig_path)
        if annotations is None:
            return False  # validation failed

        try:
            self.doc.save_with_annotations(self.path, annotations, self.zoom)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{exc}")
            return False

        self._signature = None
        self._texts.clear()
        self.render_all_pages(preserve_scroll=True)
        return True

    def save_as(self, target_path: str, sig_path: str | None) -> bool:
        """Save a copy to ``target_path``; stamps the annotations if placed.

        Leaves the open document untouched on disk, so the user can keep working
        on the original.
        """
        if not self.doc.is_open:
            return False

        annotations = []
        if self.has_annotations:
            ann_list = self._collect_annotations(sig_path)
            if ann_list is None:
                return False
            annotations = ann_list

        try:
            self.doc.save_with_annotations(target_path, annotations, self.zoom)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", f"Could not save:\n{exc}")
            return False

        return True

    def print_to(self, printer) -> None:
        """Render every page onto ``printer`` (a configured QPrinter)."""
        if not self.doc.is_open:
            return
        painter = QPainter(printer)
        try:
            dpi = printer.resolution()
            for i in range(self.doc.page_count):
                if i > 0:
                    printer.newPage()
                img = self.doc.render_page_for_print(i, dpi)
                target = painter.viewport()
                iw, ih = img.width(), img.height()
                tw, th = target.width(), target.height()
                if not (iw and ih and tw and th):
                    continue
                scale = min(tw / iw, th / ih)
                w = iw * scale
                h = ih * scale
                x = (tw - w) / 2.0
                y = (th - h) / 2.0
                painter.drawImage(QRectF(x, y, w, h), img)
        finally:
            painter.end()

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
