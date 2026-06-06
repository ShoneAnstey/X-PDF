"""Main application window: tab host, toolbar, and signature actions.

Each open PDF lives in its own DocumentTab. The toolbar actions operate on the
currently active tab.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

import config
from document_tab import DocumentTab
from signature_processing import prepare_signature

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp)"
PDF_FILTER = "PDF files (*.pdf)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("XPDF")
        self.resize(1000, 800)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._update_status)
        self.setCentralWidget(self.tabs)

        self._build_actions()
        self._build_toolbar()
        self._update_status()

        geometry = config.get_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

    # ----- current tab helper ------------------------------------------------
    def current_tab(self) -> DocumentTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, DocumentTab) else None

    # ----- UI construction ---------------------------------------------------
    def _build_actions(self) -> None:
        self.act_open = QAction("Open", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_dialog)

        self.act_close_tab = QAction("Close Tab", self)
        self.act_close_tab.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_W))
        self.act_close_tab.triggered.connect(
            lambda: self.close_tab(self.tabs.currentIndex())
        )
        self.addAction(self.act_close_tab)

        self.act_prev = QAction("Previous", self)
        self.act_prev.setShortcut(QKeySequence(Qt.Key_PageUp))
        self.act_prev.triggered.connect(lambda: self._on_tab(lambda t: t.prev_page()))

        self.act_next = QAction("Next", self)
        self.act_next.setShortcut(QKeySequence(Qt.Key_PageDown))
        self.act_next.triggered.connect(lambda: self._on_tab(lambda t: t.next_page()))

        self.act_zoom_in = QAction("Zoom In", self)
        self.act_zoom_in.setShortcut(QKeySequence.ZoomIn)
        self.act_zoom_in.triggered.connect(lambda: self._on_tab(lambda t: t.zoom_in()))

        self.act_zoom_out = QAction("Zoom Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.ZoomOut)
        self.act_zoom_out.triggered.connect(lambda: self._on_tab(lambda t: t.zoom_out()))

        self.act_fit = QAction("Fit Width", self)
        self.act_fit.triggered.connect(lambda: self._on_tab(lambda t: t.fit_width()))

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

    def _on_tab(self, fn) -> None:
        tab = self.current_tab()
        if tab is not None:
            fn(tab)

    # ----- document handling -------------------------------------------------
    def open_dialog(self) -> None:
        start_dir = config.get_last_dir() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", start_dir, PDF_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        # If the file is already open, just focus its tab.
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, DocumentTab) and widget.path == path:
                self.tabs.setCurrentIndex(i)
                return
        try:
            tab = DocumentTab(path)
        except Exception as exc:  # noqa: BLE001 - surface any load error
            QMessageBox.critical(self, "Open failed", f"Could not open PDF:\n{exc}")
            return
        tab.changed.connect(self._update_status)
        config.set_last_dir(os.path.dirname(path))
        index = self.tabs.addTab(tab, tab.title)
        self.tabs.setTabToolTip(index, path)
        self.tabs.setCurrentIndex(index)
        self._update_status()

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if isinstance(widget, DocumentTab):
            if not widget._ok_to_discard_signature():
                return
            widget.close_document()
        self.tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        self._update_status()

    # ----- signature ---------------------------------------------------------
    def set_signature_image(self) -> None:
        start_dir = (
            os.path.dirname(config.get_signature_path() or "")
            or os.path.expanduser("~")
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose signature image", start_dir, IMAGE_FILTER
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Invalid image", "That file isn't a readable image.")
            return
        try:
            prepared = os.path.join(config.cache_dir(), "signature.png")
            prepare_signature(path, prepared)
        except ValueError as exc:
            QMessageBox.warning(self, "Couldn't prepare signature", str(exc))
            return
        config.set_signature_path(prepared)
        self.statusBar().showMessage(
            "Signature ready — background removed automatically.", 4000
        )

    def add_signature(self) -> None:
        tab = self.current_tab()
        if tab is None:
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
        if tab.add_signature(sig_path):
            self.statusBar().showMessage(
                "Drag to position, drag the corner to resize, then Sign & Save.", 5000
            )

    def save_signed(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if not tab.has_signature:
            QMessageBox.information(
                self, "No signature", "Add your signature before saving."
            )
            return
        if tab.save_signed(config.get_signature_path()):
            self.statusBar().showMessage("Signed and saved.", 4000)

    # ----- status / lifecycle ------------------------------------------------
    def _update_status(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            self.status_label.setText(tab.status_text())
            self.setWindowTitle(f"XPDF — {tab.title}")
        else:
            self.status_label.setText("No document")
            self.setWindowTitle("XPDF")

    def closeEvent(self, event) -> None:
        config.set_window_geometry(self.saveGeometry())
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, DocumentTab):
                widget.close_document()
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
        # Open every dropped PDF in its own tab.
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_path(path)
