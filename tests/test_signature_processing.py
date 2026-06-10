"""Tests for the signature photo -> transparent PNG pipeline."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from signature_processing import prepare_signature


def _photo(path: str, paper=(228, 225, 220), ink=(35, 40, 90)) -> None:
    """A fake signature photo: off-white paper with a dark 'ink' stroke."""
    img = Image.new("RGB", (400, 200), paper)
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 80, 280, 120), fill=ink)
    img.save(path, "JPEG", quality=90)


def test_photo_background_removed_and_cropped(tmp_path):
    src = str(tmp_path / "photo.jpg")
    out = str(tmp_path / "sig.png")
    _photo(src)

    assert prepare_signature(src, out) == out
    result = Image.open(out)
    assert result.mode == "RGBA"

    # Cropped down to the ink plus padding, well under the full photo size.
    assert result.width < 400 and result.height < 200

    alpha = result.getchannel("A")
    # Corners are paper: fully transparent.
    assert alpha.getpixel((0, 0)) == 0
    # Centre of the stroke is ink: fully opaque.
    assert alpha.getpixel((result.width // 2, result.height // 2)) == 255

    # Ink colour is preserved (blue pen stays blue), not flattened to black.
    r, g, b, _ = result.getpixel((result.width // 2, result.height // 2))
    assert b > r  # our fake ink is blue-ish


def test_transparent_png_passes_through(tmp_path):
    src = str(tmp_path / "prepared.png")
    out = str(tmp_path / "sig.png")
    img = Image.new("RGBA", (300, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((100, 50, 200, 100), fill=(10, 10, 10, 255))
    img.save(src, "PNG")

    prepare_signature(src, out)
    result = Image.open(out)
    assert result.mode == "RGBA"
    # Existing transparency respected; image just auto-cropped.
    assert result.width < 300 and result.height < 150
    assert result.getchannel("A").getpixel((0, 0)) == 0


def test_blank_paper_raises(tmp_path):
    src = str(tmp_path / "blank.jpg")
    out = str(tmp_path / "sig.png")
    Image.new("RGB", (200, 100), (230, 230, 228)).save(src, "JPEG")
    with pytest.raises(ValueError, match="No signature"):
        prepare_signature(src, out)


def test_unreadable_file_raises(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("not an image")
    with pytest.raises(ValueError, match="Could not read image"):
        prepare_signature(str(src), str(tmp_path / "sig.png"))
