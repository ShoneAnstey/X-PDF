"""Thin wrapper around PyMuPDF (fitz) for rendering and stamping a single PDF.

Keeps all PDF-specific logic out of the Qt UI code. Coordinates exposed to the UI
are in *rendered pixel* space at the current zoom; conversion to PDF points happens
here when stamping.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import fitz  # PyMuPDF
from PySide6.QtGui import QImage, QPixmap


class PdfDocument:
    """Loads a PDF and renders / stamps pages.

    A page is rendered at ``zoom`` (1.0 == 72 dpi, the PDF's native unit). The same
    ``zoom`` is used to map a signature rectangle from screen pixels back to PDF
    points when stamping, so what you see is what gets saved.
    """

    def __init__(self) -> None:
        self._doc: fitz.Document | None = None
        self.path: str | None = None

    # ----- lifecycle ---------------------------------------------------------
    def load(self, path: str) -> None:
        self.close()
        self._doc = fitz.open(path)
        self.path = path

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self.path = None

    @property
    def is_open(self) -> bool:
        return self._doc is not None

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc is not None else 0

    # ----- rendering ---------------------------------------------------------
    def render_page(self, index: int, zoom: float, dpr: float = 1.0) -> QPixmap:
        """Render page ``index`` to a QPixmap at the given zoom factor.

        ``dpr`` is the display's device-pixel ratio. The page is rasterized at
        ``zoom * dpr`` for crisp text on HiDPI screens, and the returned pixmap is
        tagged with that ratio so it still occupies ``zoom``-sized logical space.
        """
        if self._doc is None:
            raise RuntimeError("No document open")
        page = self._doc[index]
        scale = zoom * dpr
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
        )
        # Copy so the QImage owns its buffer (pix.samples is freed with pix).
        pixmap = QPixmap.fromImage(image.copy())
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    def page_size_points(self, index: int) -> tuple[float, float]:
        """Return (width, height) of the page in PDF points."""
        if self._doc is None:
            raise RuntimeError("No document open")
        rect = self._doc[index].rect
        return rect.width, rect.height

    # ----- stamping ----------------------------------------------------------
    def stamp_and_save(
        self,
        page_index: int,
        signature_path: str,
        rect_pixels: tuple[float, float, float, float],
        zoom: float,
    ) -> None:
        """Insert ``signature_path`` onto a page and overwrite the original file.

        ``rect_pixels`` is (x0, y0, x1, y1) in rendered-pixel coordinates at ``zoom``.
        It is converted to PDF points by dividing by ``zoom``.

        The signature is stamped into a separate working copy, not the open
        document, so a failed save never leaves the in-memory document mutated
        (which would otherwise double-stamp on a retry). PyMuPDF cannot save back
        to the path it currently has open, so we write to a temporary file in the
        same directory and atomically replace the original, then reopen it.
        """
        if self._doc is None or self.path is None:
            raise RuntimeError("No document open")

        x0, y0, x1, y1 = rect_pixels
        pdf_rect = fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)

        target = self.path
        directory = os.path.dirname(os.path.abspath(target)) or "."
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=directory)
        os.close(fd)

        # Stamp a byte-for-byte copy of the original and save incrementally, so all
        # document-level structure (metadata, bookmarks/outline, named destinations,
        # attachments, form fields) is preserved -- rebuilding a new PDF from
        # inserted pages would silently drop all of that. The open document stays
        # untouched until the replace succeeds, so a retry after a failure can't
        # double-stamp.
        try:
            shutil.copyfile(target, tmp_path)
            work = fitz.open(tmp_path)
            try:
                work[page_index].insert_image(
                    pdf_rect,
                    filename=signature_path,
                    keep_proportion=True,
                    overlay=True,
                )
                work.save(
                    tmp_path,
                    incremental=True,
                    encryption=fitz.PDF_ENCRYPT_KEEP,
                )
            finally:
                work.close()
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        # Release the original handle, then atomically replace and reopen.
        self._doc.close()
        self._doc = None
        try:
            os.replace(tmp_path, target)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            self._doc = fitz.open(target)
            self.path = target

    def stamp_to(
        self,
        target_path: str,
        page_index: int,
        signature_path: str,
        rect_pixels: tuple[float, float, float, float],
        zoom: float,
    ) -> None:
        """Save a signed copy to ``target_path`` without touching the open file.

        When ``target_path`` is the currently-open document, delegate to
        :meth:`stamp_and_save` so the in-memory document is replaced and reopened
        atomically; otherwise copy the source to the target and stamp there.
        """
        if self._doc is None or self.path is None:
            raise RuntimeError("No document open")
        if os.path.abspath(target_path) == os.path.abspath(self.path):
            self.stamp_and_save(page_index, signature_path, rect_pixels, zoom)
            return

        x0, y0, x1, y1 = rect_pixels
        pdf_rect = fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)
        shutil.copyfile(self.path, target_path)
        work = fitz.open(target_path)
        try:
            work[page_index].insert_image(
                pdf_rect,
                filename=signature_path,
                keep_proportion=True,
                overlay=True,
            )
            work.save(target_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        finally:
            work.close()

    def copy_to(self, target_path: str) -> None:
        """Copy the currently-open file to ``target_path`` (no-op if same path)."""
        if self.path is None:
            raise RuntimeError("No document open")
        if os.path.abspath(target_path) == os.path.abspath(self.path):
            return
        shutil.copyfile(self.path, target_path)

    # ----- search ------------------------------------------------------------
    def search_page(self, index: int, text: str) -> list[fitz.Rect]:
        """Return rectangles (PDF points) where ``text`` matches on page ``index``."""
        if self._doc is None:
            raise RuntimeError("No document open")
        if not text:
            return []
        return self._doc[index].search_for(text)

    # ----- printing ----------------------------------------------------------
    def render_page_for_print(self, index: int, dpi: int) -> QImage:
        """Render page ``index`` as a QImage at the given DPI for sending to a printer."""
        if self._doc is None:
            raise RuntimeError("No document open")
        page = self._doc[index]
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
        )
        return image.copy()
