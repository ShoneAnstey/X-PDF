"""Thin wrapper around PyMuPDF (fitz) for rendering and stamping a single PDF.

Keeps all PDF-specific logic out of the Qt UI code. Coordinates exposed to the UI
are in *rendered pixel* space at the current zoom; conversion to PDF points happens
here when stamping.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Literal

import fitz  # PyMuPDF
from PySide6.QtGui import QImage, QPixmap


@dataclass
class PdfAnnotation:
    """A user-placed annotation to be stamped onto a page."""
    page_index: int
    rect_pixels: tuple[float, float, float, float]  # (x0, y0, x1, y1) local to target page at `zoom`
    type: Literal["image", "text"]

    # Image properties
    image_path: str | None = None
    rotation: int = 0

    # Text properties
    text: str = ""


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

    def _apply_annotations_to_work(self, work: fitz.Document, annotations: list[PdfAnnotation], zoom: float) -> None:
        """Apply a list of annotations to the opened PyMuPDF document."""
        for ann in annotations:
            x0, y0, x1, y1 = ann.rect_pixels
            pdf_rect = fitz.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom)

            if ann.type == "image":
                work[ann.page_index].insert_image(
                    pdf_rect,
                    filename=ann.image_path,
                    keep_proportion=True,
                    overlay=True,
                    rotate=ann.rotation,
                )
            elif ann.type == "text":
                # We need to scale the font size properly. QGraphicsTextItem with a 16pt
                # font corresponds to 16 PDF points at zoom=1.0.
                # insert_textbox handles text wrapping, but needs slightly more room than
                # Qt's tight bounding box to prevent it from rejecting the text.
                text_rect = pdf_rect + (-5, -5, 5, 5)
                rc = work[ann.page_index].insert_textbox(
                    text_rect,
                    ann.text,
                    fontsize=16,
                    fontname="helv",
                    color=(0, 0, 0),
                    align=0,
                )
                if rc < 0:
                    # If it STILL doesn't fit, use insert_text directly as a fallback
                    # so data is never silently dropped.
                    work[ann.page_index].insert_text(
                        (pdf_rect.x0, pdf_rect.y0 + 12),
                        ann.text,
                        fontsize=16,
                        fontname="helv",
                        color=(0, 0, 0),
                    )

    # ----- stamping ----------------------------------------------------------
    def save_with_annotations(
        self,
        target_path: str,
        annotations: list[PdfAnnotation],
        zoom: float,
    ) -> None:
        """Stamp annotations (images/text) into target_path.

        If target_path is the currently open document, it writes to a temp file and
        replaces the original atomically. Otherwise it copies the source and stamps.
        """
        if self._doc is None or self.path is None:
            raise RuntimeError("No document open")

        target = os.path.abspath(target_path)
        is_open_doc = (target == os.path.abspath(self.path))
        target_save = target

        if is_open_doc:
            directory = os.path.dirname(target) or "."
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=directory)
            os.close(fd)
            target_save = tmp_path

        try:
            shutil.copyfile(self.path, target_save)
            work = fitz.open(target_save)
            try:
                self._apply_annotations_to_work(work, annotations, zoom)
                work.save(
                    target_save,
                    incremental=True,
                    encryption=fitz.PDF_ENCRYPT_KEEP,
                )
            finally:
                work.close()
        except Exception:
            if is_open_doc and os.path.exists(target_save):
                os.remove(target_save)
            raise

        if is_open_doc:
            self._doc.close()
            self._doc = None
            try:
                os.replace(target_save, target)
            finally:
                if os.path.exists(target_save):
                    os.remove(target_save)
                self._doc = fitz.open(target)
                self.path = target



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
