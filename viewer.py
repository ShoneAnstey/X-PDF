"""Main application window: tab host, toolbar, and signature actions.

Each open PDF lives in its own DocumentTab. The toolbar actions operate on the
currently active tab.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

import config
from document_tab import DocumentTab
from sidebar import Sidebar
from signature_processing import prepare_signature
from text_item import TextItem
from version import build_metadata, version_string

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp)"
PDF_FILTER = "PDF files (*.pdf)"

# A compact dark theme for the app chrome. PDF pages keep their own (usually
# white) background; only the surrounding UI is darkened.
_DARK_STYLESHEET = """
QWidget { background-color: #2b2b2b; color: #e0e0e0; }
QMenuBar, QMenu { background-color: #2b2b2b; color: #e0e0e0; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #3d6ea5; }
QToolBar { background-color: #333333; border: none; }
QToolButton { background-color: transparent; color: #e0e0e0; padding: 4px; }
QToolButton:hover { background-color: #3d6ea5; }
QTabBar::tab { background: #333333; color: #cccccc; padding: 6px 12px; }
QTabBar::tab:selected { background: #2b2b2b; color: #ffffff; }
QTabWidget::pane { border: 1px solid #444444; }
QListWidget, QTreeWidget { background-color: #232323; color: #e0e0e0; }
QListWidget::item:selected, QTreeWidget::item:selected { background-color: #3d6ea5; }
QLineEdit { background-color: #232323; color: #e0e0e0; border: 1px solid #555555; }
QPushButton { background-color: #444444; color: #e0e0e0; padding: 4px 10px; }
QPushButton:hover { background-color: #3d6ea5; }
QStatusBar { background-color: #333333; color: #cccccc; }
QGraphicsView { background-color: #1e1e1e; }
"""

SIGNATURE_INSTRUCTIONS = (
    "How to set up your signature:\n"
    "\n"
    "  1. Sign your name on a clean, blank piece of paper.\n"
    "  2. Take a photo with your phone in good light.\n"
    "  3. Transfer the photo to this computer (email, AirDrop, USB \u2014 any way).\n"
    "  4. Click \u201cChoose image\u2026\u201d below and pick that photo.\n"
    "\n"
    "Inkstone removes the paper background automatically, so the signature can be\n"
    "dropped onto a PDF page as if signed directly on the document."
)


class SignatureSetupDialog(QDialog):
    """Walks the user through capturing and importing a signature photo."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle("Signature setup")
        self.setModal(True)
        self.resize(520, 360)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(SIGNATURE_INSTRUCTIONS))

        self._status = QLabel(self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._preview = QLabel(self)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumHeight(120)
        layout.addWidget(self._preview, 1)

        choose = QPushButton("Choose image\u2026", self)
        choose.clicked.connect(self._choose_image)
        layout.addWidget(choose)

        remove = QPushButton("Remove signature", self)
        remove.setToolTip("Forget the stored signature and delete the cached image")
        remove.clicked.connect(self._remove_signature)
        layout.addWidget(remove)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_preview()

    def _refresh_preview(self) -> None:
        path = config.get_signature_path()
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self._preview.setPixmap(
                    pix.scaled(
                        420,
                        140,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                self._status.setText(f"Current signature: {path}")
                return
        self._preview.clear()
        self._status.setText("No signature set yet.")

    def _choose_image(self) -> None:
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
        self._refresh_preview()

    def _remove_signature(self) -> None:
        """Forget the stored signature; delete the cached copy if we made it."""
        path = config.get_signature_path()
        config.clear_signature_path()
        if path:
            try:
                # Only delete files inside our own cache dir -- never a file the
                # user picked directly from their disk.
                cache = os.path.abspath(config.cache_dir())
                if os.path.dirname(os.path.abspath(path)) == cache:
                    os.remove(path)
            except OSError:
                pass
        self._refresh_preview()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Inkstone {version_string()}")
        self.resize(1000, 800)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Navigation sidebar (thumbnails + outline) on the left, pages on the right.
        self.sidebar = Sidebar(self)
        self.sidebar.page_selected.connect(self._on_sidebar_page_selected)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 780])
        self._splitter = splitter
        self.setCentralWidget(splitter)

        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self._apply_theme(config.get_dark_mode())
        self.sidebar.setVisible(config.get_sidebar_visible())
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

        self.act_set_sig = QAction("Signature setup...", self)
        self.act_set_sig.triggered.connect(self.open_signature_setup)

        self.act_add_sig = QAction("Place signature on page", self)
        self.act_add_sig.triggered.connect(self.add_signature)

        self.act_rotate_sig_cw = QAction("Rotate signature 90° clockwise", self)
        self.act_rotate_sig_cw.setShortcut(QKeySequence(Qt.Key_R))
        self.act_rotate_sig_cw.triggered.connect(lambda: self.rotate_signature(90))
        self.addAction(self.act_rotate_sig_cw)

        self.act_rotate_sig_ccw = QAction(
            "Rotate signature 90° counter-clockwise", self
        )
        self.act_rotate_sig_ccw.setShortcut(QKeySequence(Qt.SHIFT | Qt.Key_R))
        self.act_rotate_sig_ccw.triggered.connect(lambda: self.rotate_signature(-90))
        self.addAction(self.act_rotate_sig_ccw)

        self.act_add_text = QAction("Add text / Typewriter", self)
        self.act_add_text.setShortcut(QKeySequence(Qt.CTRL | Qt.Key_T))
        self.act_add_text.triggered.connect(self.add_text_annotation)
        self.addAction(self.act_add_text)

        self.act_add_highlight = QAction("Highlight", self)
        self.act_add_highlight.setShortcut(QKeySequence("Ctrl+H"))
        self.act_add_highlight.triggered.connect(self.add_highlight_annotation)
        self.addAction(self.act_add_highlight)

        self.act_undo = QAction("Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.undo_annotation)
        self.addAction(self.act_undo)

        self.act_append_pdf = QAction("Append PDF...", self)
        self.act_append_pdf.triggered.connect(self.append_pdf_dialog)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self.save_signed)

        self.act_save_as = QAction("Save As...", self)
        self.act_save_as.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_S))
        self.act_save_as.triggered.connect(self.save_as_dialog)

        self.act_find = QAction("Find", self)
        self.act_find.setShortcut(QKeySequence.Find)
        self.act_find.triggered.connect(self.show_find)

        self.act_print = QAction("Print", self)
        self.act_print.setShortcut(QKeySequence.Print)
        self.act_print.triggered.connect(self.print_document)

        self.act_toggle_sidebar = QAction("Show Sidebar", self)
        self.act_toggle_sidebar.setCheckable(True)
        self.act_toggle_sidebar.setChecked(config.get_sidebar_visible())
        self.act_toggle_sidebar.setShortcut(QKeySequence(Qt.Key_F9))
        self.act_toggle_sidebar.triggered.connect(self.toggle_sidebar)
        self.addAction(self.act_toggle_sidebar)

        self.act_dark_mode = QAction("Dark Mode", self)
        self.act_dark_mode.setCheckable(True)
        self.act_dark_mode.setChecked(config.get_dark_mode())
        self.act_dark_mode.triggered.connect(self.toggle_dark_mode)

        self.act_about = QAction("About Inkstone", self)
        self.act_about.triggered.connect(self.show_about)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.act_open)

        self.menu_recent = file_menu.addMenu("Open Recent")
        self._populate_recent_menu()

        file_menu.addSeparator()
        file_menu.addAction(self.act_save_as)
        file_menu.addAction(self.act_append_pdf)
        file_menu.addAction(self.act_print)
        file_menu.addSeparator()
        file_menu.addAction(self.act_close_tab)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.act_toggle_sidebar)
        view_menu.addAction(self.act_dark_mode)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.act_about)

    def _populate_recent_menu(self) -> None:
        self.menu_recent.clear()
        recent = config.get_recent_files()
        # Prune entries whose files no longer exist so the stored list doesn't
        # accumulate dead paths forever.
        existing = [p for p in recent if os.path.exists(p)]
        if existing != recent:
            config.set_recent_files(existing)
        if not existing:
            empty = self.menu_recent.addAction("No recent files")
            empty.setEnabled(False)
            return

        for path in existing:
            # Use a default arg to bind the path
            action = self.menu_recent.addAction(os.path.basename(path))
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_path(p))

        self.menu_recent.addSeparator()
        clear = self.menu_recent.addAction("Clear Recent Files")
        clear.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self) -> None:
        config.clear_recent_files()
        self._populate_recent_menu()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        # Show labels under each button so the new actions are discoverable for
        # users who don't know the keyboard shortcuts.
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
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
        toolbar.addAction(self.act_find)
        toolbar.addAction(self.act_print)
        toolbar.addSeparator()

        toolbar.addAction(self.act_add_text)
        toolbar.addAction(self.act_add_highlight)
        toolbar.addSeparator()

        # Single Signature dropdown replaces the old Set/Add/Sign buttons whose
        # names were too similar to tell apart at a glance.
        sig_menu = QMenu(self)
        sig_menu.addAction(self.act_set_sig)
        sig_menu.addAction(self.act_add_sig)
        sig_menu.addSeparator()
        sig_menu.addAction(self.act_rotate_sig_cw)
        sig_menu.addAction(self.act_rotate_sig_ccw)
        sig_menu.addSeparator()
        sig_menu.addAction(self.act_save)
        self._sig_menu = sig_menu

        sig_button = QToolButton(self)
        sig_button.setText("Signature")
        sig_button.setToolTip("Set up, place, rotate, or save your signature")
        sig_button.setPopupMode(QToolButton.InstantPopup)
        sig_button.setMenu(sig_menu)
        toolbar.addWidget(sig_button)

        toolbar.addAction(self.act_save_as)

        self.status_label = QLabel("No document")
        self.statusBar().addPermanentWidget(self.status_label)

        # Apply tooltips that include the shortcut hint, e.g. "Find (Ctrl+F)".
        for action in (
            self.act_open, self.act_prev, self.act_next,
            self.act_zoom_out, self.act_zoom_in, self.act_fit,
            self.act_find, self.act_print,
            self.act_add_text, self.act_add_highlight,
            self.act_set_sig, self.act_add_sig,
            self.act_rotate_sig_cw, self.act_rotate_sig_ccw,
            self.act_save, self.act_save_as,
        ):
            shortcut = action.shortcut().toString()
            label = action.text().replace("&&", "&").replace("...", "")
            action.setToolTip(f"{label} ({shortcut})" if shortcut else label)

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
        # Normalise so the same file via different spellings (relative path,
        # drag-drop URL, recent entry) maps to one tab.
        path = os.path.abspath(path)
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
        tab.structure_changed.connect(self._refresh_sidebar)
        tab.changed.connect(self._sync_sidebar_highlight)
        config.set_last_dir(os.path.dirname(path))
        config.add_recent_file(path)
        self._populate_recent_menu()
        index = self.tabs.addTab(tab, tab.title)
        self.tabs.setTabToolTip(index, path)
        # Making the new tab current fires currentChanged -> _on_tab_changed,
        # which updates the status bar and rebuilds the sidebar exactly once.
        self.tabs.setCurrentIndex(index)

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if isinstance(widget, DocumentTab):
            if not widget.ok_to_discard_annotations():
                return
            widget.close_document()
        self.tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        self._update_status()

    # ----- signature ---------------------------------------------------------
    def open_signature_setup(self) -> None:
        """Open the signature setup dialog (instructions + image picker)."""
        dialog = SignatureSetupDialog(self)
        dialog.exec()

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
                "Open 'Signature ▾ → Signature setup...' to choose your signature image first.",
            )
            return
        if tab.add_signature(sig_path):
            self.statusBar().showMessage(
                "Drag to position, drag the corner to resize, press R to rotate, then Sign & Save.",
                6000,
            )

    def add_text_annotation(self) -> None:
        tab = self.current_tab()
        if tab is None:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        if tab.add_text():
            self.statusBar().showMessage(
                "Type your text, drag to position, then Save.",
                5000,
            )

    def add_highlight_annotation(self) -> None:
        tab = self.current_tab()
        if tab is None:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        if tab.add_highlight():
            self.statusBar().showMessage(
                "Drag over the text, drag the corner to resize, Delete to remove, then Save.",
                6000,
            )

    def undo_annotation(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        # If the user is editing inside a text box, Ctrl+Z must undo typing in
        # that box, not remove the most recently placed annotation.
        focus_item = tab.scene.focusItem()
        if isinstance(focus_item, TextItem):
            focus_item.document().undo()
            return
        if tab.undo_annotation():
            self.statusBar().showMessage("Annotation undone.", 3000)
        else:
            self.statusBar().showMessage("Nothing to undo.", 3000)

    def append_pdf_dialog(self) -> None:
        tab = self.current_tab()
        if tab is None:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        start_dir = config.get_last_dir() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Append PDF to end of document", start_dir, PDF_FILTER
        )
        if not path:
            return
        if tab.append_pdf(path):
            self.statusBar().showMessage(
                f"Appended {os.path.basename(path)}.", 4000
            )

    def rotate_signature(self, delta_deg: int) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if not tab.rotate_signature(delta_deg):
            self.statusBar().showMessage(
                "Place a signature first (Signature ▾ → Place signature on page).",
                4000,
            )

    def save_signed(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if not tab.has_annotations:
            QMessageBox.information(
                self, "No annotations",
                "Add a signature, text, or highlight before saving.",
            )
            return
        if tab.save_signed(config.get_signature_path()):
            self.statusBar().showMessage("Saved.", 4000)

    def save_as_dialog(self) -> None:
        tab = self.current_tab()
        if tab is None:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        start_dir = config.get_last_dir() or os.path.expanduser("~")
        suggested = os.path.join(start_dir, tab.title)
        target, _ = QFileDialog.getSaveFileName(
            self, "Save PDF As", suggested, PDF_FILTER
        )
        if not target:
            return
        if not target.lower().endswith(".pdf"):
            target += ".pdf"
        if tab.save_as(target, config.get_signature_path()):
            config.set_last_dir(os.path.dirname(target))
            self.statusBar().showMessage(
                f"Saved {os.path.basename(target)}", 4000
            )

    def show_find(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.show_find_bar()

    def print_document(self) -> None:
        tab = self.current_tab()
        if tab is None:
            QMessageBox.information(self, "No document", "Open a PDF first.")
            return
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.Accepted:
            return
        tab.print_to(printer)
        self.statusBar().showMessage("Sent to printer.", 4000)

    # ----- status / lifecycle ------------------------------------------------
    def show_about(self) -> None:
        meta = build_metadata()
        commit = meta["commit"] or "development build"
        lines = [
            f"<b>Inkstone {version_string()}</b>",
            "A simple PDF reader with paper-photo signature stamping.",
            "",
            f"Commit: {commit}",
        ]
        if meta["date"]:
            lines.append(f"Built: {meta['date']}")
        lines.append("")
        lines.append("Released into the public domain (The Unlicense).")
        QMessageBox.about(self, "About Inkstone", "<br>".join(lines))

    def _update_status(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            self.status_label.setText(tab.status_text())
            self.setWindowTitle(f"Inkstone {version_string()} — {tab.title}")
        else:
            self.status_label.setText("No document")
            self.setWindowTitle(f"Inkstone {version_string()}")

    # ----- sidebar & theme ---------------------------------------------------
    def _on_tab_changed(self, _index: int = -1) -> None:
        """Refresh the status bar and rebuild the sidebar for the active tab."""
        self._update_status()
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        tab = self.current_tab()
        if tab is None:
            self.sidebar.clear()
            return
        self.sidebar.load_document(tab.doc)
        self.sidebar.highlight_page(tab.current_page)

    def _sync_sidebar_highlight(self) -> None:
        tab = self.current_tab()
        if tab is not None:
            self.sidebar.highlight_page(tab.current_page)

    def _on_sidebar_page_selected(self, index: int) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.goto_page(index)

    def toggle_sidebar(self, checked: bool) -> None:
        self.sidebar.setVisible(checked)
        config.set_sidebar_visible(checked)

    def toggle_dark_mode(self, checked: bool) -> None:
        config.set_dark_mode(checked)
        self._apply_theme(checked)

    def _apply_theme(self, dark: bool) -> None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        app.setStyleSheet(_DARK_STYLESHEET if dark else "")

    def closeEvent(self, event) -> None:
        # Warn before discarding any placed-but-unsaved annotations.
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, DocumentTab) and not widget.ok_to_discard_annotations():
                event.ignore()
                return
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
