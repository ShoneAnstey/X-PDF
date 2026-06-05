"""Main application window: toolbar, page navigation, zoom, signature, save."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

import config
from pdf_document import PdfDocument
from signature_item import SignatureItem

ZOOM_MIN = 0.25
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp)"
PDF_FILTER = "PDF files (*.pdf)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("XPC PDF")
        self.resize(1000, 800)

        self.doc = PdfDocument()
        self.page_index = 0
        self.zoom = 1.5
        self._page_item: QGraphicsPixmapItem | None = None
        self._signature: SignatureItem | None = None

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(Qt.darkGray)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setCentralWidget(self.view)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_toolbar()
        self._update_status()

        geometry = config.get_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

    # ----- UI construction ---------------------------------------------------
    def _build_actions(self) -> None:
        self.act_open = QAction("Open", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_dialog)

        self.act_prev = QAction("Previous", self)
        self.act_prev.setShortcut(QKeySequence(Qt.Key_PageUp))
        self.act_prev.triggered.connect(self.prev_page)

        self.act_next = QAction("Next", self)
        self.act_next.setShortcut(QKeySequence(Qt.Key_PageDown))
        self.act_next.triggered.connect(self.next_page)

        self.act_zoom_in = QAction("Zoom In", self)
        self.act_zoom_in.setShortcut(QKeySequence.ZoomIn)
        self.act_zoom_in.triggered.connect(self.zoom_in)

        self.act_zoom_out = QAction("Zoom Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.ZoomOut)
        self.act_zoom_out.triggered.connect(self.zoom_out)

        self.act_fit = QAction("Fit Width", self)
        self.act_fit.triggered.connect(self.fit_width)

        self.act_set_sig = QAction("Set Signature", self)
        self.act_set_sig.triggered.connect(self.set_signature_image)

        self.act_add_sig = QAction("Add Signature", self)
        self.act_add_sig.triggered.connect(self.add_signature)

        self.act_save = QAction("Sign && Save", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self.save_signed)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.act_open)
        toolbar.addSeparator()
        toolbar.addAction(self.act_prev)
        toolbar.addAction(self.act_next)
        toolbar.addSeparator()
        toolbar.addAction(self.act_zoom_out)
        toolbar.addAction(self.act_zoom_in)
        toolbar.addAction(self.act_fit)
        toolbar.addSeparator()
        toolbar.addAction(self.act_set_sig)
        toolbar.addAction(self.act_add_sig)
        toolbar.addAction(self.act_save)

        self.status_label = QLabel("No document")
        self.statusBar().addPermanentWidget(self.status_label)

    # ----- document handling -------------------------------------------------
    def open_dialog(self) -> None:
        start_dir = config.get_last_dir() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", start_dir, PDF_FILTER
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        try:
            self.doc.load(path)
        except Exception as exc:  # noqa: BLE001 - surface any load error to the user
            QMessageBox.critical(self, "Open failed", f"Could not open PDF:\n{exc}")
            return
        config.set_last_dir(os.path.dirname(path))
        self.page_index = 0
        self._signature = None
        self.setWindowTitle(f"XPC PDF — {os.path.basename(path)}")
        self.render_current_page()

    def render_current_page(self) -> None:
        if not self.doc.is_open:
            return
        # Resizing/replacing the page drops any unsaved signature overlay.
        keep_sig = self._signature
        self.scene.clear()
        self._page_item = None
        self._signature = None

        pixmap = self.doc.render_page(self.page_index, self.zoom)
        self._page_item = self.scene.addPixmap(pixmap)
        self._page_item.setZValue(0)
        self.scene.setSceneRect(self._page_item.boundingRect())

        # Re-add the signature so zoom/page redraws don't lose it.
        if keep_sig is not None:
            self.scene.addItem(keep_sig)
            self._signature = keep_sig
        self._update_status()

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
    def set_signature_image(self) -> None:
        start_dir = os.path.dirname(config.get_signature_path() or "") or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose signature image", start_dir, IMAGE_FILTER
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Invalid image", "That file isn't a readable image.")
            return
        config.set_signature_path(path)
        self.statusBar().showMessage("Signature image saved.", 3000)

    def add_signature(self) -> None:
        if not self.doc.is_open:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        sig_path = config.get_signature_path()
        if not sig_path or not os.path.exists(sig_path):
            QMessageBox.information(
                self,
                "No signature set",
                "Use 'Set Signature' to choose your signature image first.",
            )
            return
        if self._signature is not None:
            self.scene.removeItem(self._signature)
            self._signature = None
        try:
            item = SignatureItem(sig_path)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return
        # Drop near the centre of the current page.
        page_rect = self._page_item.boundingRect()
        item.setPos(
            page_rect.width() / 2 - 110,
            page_rect.height() / 2 - 40,
        )
        self.scene.addItem(item)
        item.setSelected(True)
        self._signature = item
        self.statusBar().showMessage(
            "Drag to position, drag the corner to resize, then Sign & Save.", 5000
        )

    def save_signed(self) -> None:
        if not self.doc.is_open:
            return
        if self._signature is None:
            QMessageBox.information(
                self, "No signature", "Add your signature before saving."
            )
            return
        sig_path = config.get_signature_path()
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
            return
        self._signature = None
        self.render_current_page()
        self.statusBar().showMessage("Signed and saved.", 4000)

    # ----- status / lifecycle ------------------------------------------------
    def _update_status(self) -> None:
        if self.doc.is_open:
            self.status_label.setText(
                f"Page {self.page_index + 1} / {self.doc.page_count}"
                f"    {int(self.zoom * 100)}%"
            )
        else:
            self.status_label.setText("No document")

    def closeEvent(self, event) -> None:
        config.set_window_geometry(self.saveGeometry())
        self.doc.close()
        super().closeEvent(event)

    # ----- drag & drop -------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_path(path)
                break
