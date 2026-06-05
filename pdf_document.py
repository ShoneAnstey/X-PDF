"""Thin wrapper around PyMuPDF (fitz) for rendering and stamping a single PDF.

Keeps all PDF-specific logic out of the Qt UI code. Coordinates exposed to the UI
are in *rendered pixel* space at the current zoom; conversion to PDF points happens
here when stamping.
"""

from __future__ import annotations

import os
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
    def render_page(self, index: int, zoom: float) -> QPixmap:
        """Render page ``index`` to a QPixmap at the given zoom factor."""
        if self._doc is None:
            raise RuntimeError("No document open")
        page = self._doc[index]
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
        )
        # Copy so the QImage owns its buffer (pix.samples is freed with pix).
        return QPixmap.fromImage(image.copy())

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

        PyMuPDF cannot save back to the path it currently has open, so we write to a
        temporary file in the same directory and atomically replace the original,
        then reopen the saved result.
        """
        if self._doc is None or self.path is None:
            raise RuntimeError("No document open")

        x0, y0, x1, y1 = rect_pixels
        pdf_rect = fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)

        page = self._doc[page_index]
        page.insert_image(
            pdf_rect,
            filename=signature_path,
            keep_proportion=True,
            overlay=True,
        )

        target = self.path
        directory = os.path.dirname(os.path.abspath(target)) or "."
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=directory)
        os.close(fd)
        try:
            self._doc.save(tmp_path, garbage=4, deflate=True)
            self._doc.close()
            self._doc = None
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        finally:
            # Reopen so the viewer keeps working after a save.
            if self._doc is None and os.path.exists(target):
                self._doc = fitz.open(target)
                self.path = target
