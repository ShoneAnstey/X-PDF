"""Tests for PdfDocument: page surgery, annotation stamping, search, outline."""

from __future__ import annotations

from collections.abc import Iterator

import fitz
import pytest
from PIL import Image

from pdf_document import PdfAnnotation, PdfDocument


def make_pdf(path: str, pages: int = 3, text: str = "Hello world") -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()  # default A4-ish 595x842
        page.insert_text((72, 72), f"{text} page {i + 1}", fontsize=12)
    doc.save(path)
    doc.close()


@pytest.fixture
def pdf_path(tmp_path) -> str:
    path = str(tmp_path / "sample.pdf")
    make_pdf(path)
    return path


@pytest.fixture
def doc(pdf_path) -> Iterator[PdfDocument]:
    d = PdfDocument()
    d.load(pdf_path)
    yield d
    d.close()


# ----- basics ----------------------------------------------------------------
def test_load_and_page_count(doc):
    assert doc.is_open
    assert doc.page_count == 3


def test_page_size_points(doc):
    w, h = doc.page_size_points(0)
    assert w > 0 and h > 0


def test_search_page(doc):
    assert doc.search_page(0, "page 1")
    assert not doc.search_page(0, "page 2")
    assert doc.search_page(0, "") == []


# ----- page surgery ------------------------------------------------------------
def test_delete_page(doc, pdf_path):
    version = doc.structure_version
    doc.delete_page(1)
    assert doc.page_count == 2
    assert doc.structure_version == version + 1
    assert doc.path == pdf_path
    # The file on disk was really rewritten.
    with fitz.open(pdf_path) as check:
        assert check.page_count == 2
        assert "page 1" in check[0].get_text()
        assert "page 3" in check[1].get_text()


def test_delete_only_page_raises(tmp_path):
    path = str(tmp_path / "one.pdf")
    make_pdf(path, pages=1)
    d = PdfDocument()
    d.load(path)
    try:
        with pytest.raises(ValueError):
            d.delete_page(0)
        assert d.page_count == 1
    finally:
        d.close()


def test_delete_out_of_range(doc):
    with pytest.raises(IndexError):
        doc.delete_page(99)


def test_extract_pages(doc, tmp_path):
    target = str(tmp_path / "extracted.pdf")
    doc.extract_pages(target, [2, 0])
    with fitz.open(target) as out:
        assert out.page_count == 2
        assert "page 3" in out[0].get_text()  # order preserved
        assert "page 1" in out[1].get_text()
    assert doc.page_count == 3  # source untouched


def test_extract_no_pages_raises(doc, tmp_path):
    with pytest.raises(ValueError):
        doc.extract_pages(str(tmp_path / "x.pdf"), [])


def test_extract_out_of_range_raises(doc, tmp_path):
    with pytest.raises(IndexError):
        doc.extract_pages(str(tmp_path / "x.pdf"), [99])


# ----- outline -----------------------------------------------------------------
def test_outline(tmp_path):
    path = str(tmp_path / "toc.pdf")
    src = fitz.open()
    for _ in range(3):
        src.new_page()
    src.set_toc([[1, "Chapter 1", 1], [2, "Section 1.1", 2], [1, "Chapter 2", 3]])
    src.save(path)
    src.close()

    d = PdfDocument()
    d.load(path)
    try:
        rows = d.outline()
    finally:
        d.close()
    # 1-based TOC pages are converted to 0-based indices.
    assert rows == [(1, "Chapter 1", 0), (2, "Section 1.1", 1), (1, "Chapter 2", 2)]


def test_outline_empty(doc):
    assert doc.outline() == []


# ----- annotation stamping -------------------------------------------------------
def _text_spans(path: str, page: int = 0) -> list[dict]:
    with fitz.open(path) as check:
        spans = []
        for block in check[page].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans.extend(line.get("spans", []))
        return spans


def test_save_text_annotation_fontsize_scales_with_zoom(doc, pdf_path):
    """A 16pt on-screen font at zoom 2.0 must be stamped at 8 PDF points."""
    zoom = 2.0
    ann = PdfAnnotation(
        page_index=0,
        rect_pixels=(100.0, 200.0, 500.0, 320.0),  # PDF rect (50, 100, 250, 160)
        type="text",
        text="STAMPED",
    )
    doc.save_with_annotations(pdf_path, [ann], zoom)
    spans = [s for s in _text_spans(pdf_path) if "STAMPED" in s["text"]]
    assert spans, "stamped text not found in saved PDF"
    assert spans[0]["size"] == pytest.approx(16.0 / zoom, abs=0.1)
    # And roughly where we put it (inside the padded rect).
    x0, y0, _, _ = spans[0]["bbox"]
    assert 40 <= x0 <= 60
    assert 90 <= y0 <= 170


def test_save_image_annotation(doc, pdf_path, tmp_path):
    sig = str(tmp_path / "sig.png")
    Image.new("RGBA", (60, 24), (200, 30, 30, 255)).save(sig)
    ann = PdfAnnotation(
        page_index=1,
        rect_pixels=(150.0, 150.0, 450.0, 270.0),
        type="image",
        image_path=sig,
    )
    doc.save_with_annotations(pdf_path, [ann], 1.5)
    with fitz.open(pdf_path) as check:
        assert check[1].get_images(full=True)
        assert not check[0].get_images(full=True)
    # The document was reopened in place and still works.
    assert doc.is_open and doc.page_count == 3


def test_save_as_leaves_original_untouched(doc, pdf_path, tmp_path):
    target = str(tmp_path / "copy.pdf")
    before = open(pdf_path, "rb").read()
    ann = PdfAnnotation(
        page_index=0,
        rect_pixels=(100.0, 200.0, 400.0, 300.0),
        type="text",
        text="ONLY IN COPY",
    )
    doc.save_with_annotations(target, [ann], 1.0)
    assert open(pdf_path, "rb").read() == before
    spans = [s for s in _text_spans(target) if "ONLY IN COPY" in s["text"]]
    assert spans


def test_copy_to(doc, pdf_path, tmp_path):
    target = str(tmp_path / "dup.pdf")
    doc.copy_to(target)
    assert open(target, "rb").read() == open(pdf_path, "rb").read()


# ----- thumbnails ----------------------------------------------------------------
def test_render_thumbnail_cached_and_invalidated(doc):
    a = doc.render_thumbnail(0, 100)
    assert max(a.width(), a.height()) <= 100
    assert doc.render_thumbnail(0, 100) is a  # cache hit
    doc.delete_page(2)
    assert doc.render_thumbnail(0, 100) is not a  # cache cleared by delete
