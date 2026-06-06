"""Turn a photo or scan of a signature into a transparent-background PNG.

The intended workflow is the simplest one possible: sign a blank sheet of paper,
take a photo with a phone, and open that photo as your signature. Phone photos are
not clean PNGs -- they are rotated by EXIF orientation, lit unevenly, and have an
off-white paper background rather than pure white. :func:`prepare_signature`
handles all of that:

1. Apply EXIF orientation so the image is upright.
2. If the image already has real transparency (a prepared PNG), leave the pixels
   alone and just trim the empty margins.
3. Otherwise estimate the paper tone from the border, then build a soft alpha ramp
   that makes paper-toned pixels transparent while keeping the ink -- including its
   original colour, so a blue pen stays blue -- with anti-aliased edges.
4. Auto-crop to the signature so it drops onto the page tightly.

Only Pillow is required; there is no NumPy dependency.
"""

from __future__ import annotations

from PIL import Image, ImageOps

# Alpha below this (0-255) counts as "background" when measuring the crop box.
_CROP_ALPHA_FLOOR = 20
# Pixels left around the signature after auto-cropping.
_CROP_PADDING = 12
# Fraction of the shorter side sampled from each edge to estimate paper tone.
_BORDER_FRACTION = 0.06


def _has_real_transparency(img: Image.Image) -> bool:
    """True if the image already carries a meaningful alpha channel."""
    if img.mode not in ("RGBA", "LA", "PA"):
        return False
    alpha = img.convert("RGBA").getchannel("A")
    low = alpha.getextrema()[0]
    return isinstance(low, (int, float)) and low < 250


def _estimate_paper_level(gray: Image.Image) -> int:
    """Estimate the paper brightness (0-255) from the image border.

    The border of a signature photo is almost always blank paper, so its median
    luminance is a robust paper estimate that tolerates uneven lighting better than
    a global average would.
    """
    width, height = gray.size
    margin = max(1, int(min(width, height) * _BORDER_FRACTION))

    edges = [
        gray.crop((0, 0, width, margin)),               # top
        gray.crop((0, height - margin, width, height)),  # bottom
        gray.crop((0, 0, margin, height)),               # left
        gray.crop((width - margin, 0, width, height)),   # right
    ]

    counts = [0] * 256
    for edge in edges:
        for value, count in enumerate(edge.histogram()):
            counts[value] += count

    total = sum(counts)
    if total == 0:
        return 255

    # Median is more robust to the occasional stray ink stroke near an edge.
    midpoint = total // 2
    cumulative = 0
    for value, count in enumerate(counts):
        cumulative += count
        if cumulative >= midpoint:
            return value
    return 255


def _alpha_lut(paper_level: int) -> list[int]:
    """Build a 256-entry luminance -> alpha ramp.

    Pixels at or above ``white_point`` (near paper tone) become fully transparent;
    pixels at or below ``black_point`` (clearly ink) become fully opaque; the band
    between ramps linearly so edges stay anti-aliased instead of jagged.
    """
    paper_level = max(1, paper_level)
    white_point = max(2, int(paper_level * 0.90))
    black_point = max(1, int(paper_level * 0.55))
    if white_point <= black_point:
        white_point = black_point + 1

    span = white_point - black_point
    lut: list[int] = []
    for lum in range(256):
        if lum >= white_point:
            lut.append(0)
        elif lum <= black_point:
            lut.append(255)
        else:
            lut.append(int(round((white_point - lum) / span * 255)))
    return lut


def _autocrop(img: Image.Image) -> Image.Image:
    """Crop to the visible signature plus a small padding margin."""
    alpha = img.getchannel("A")
    mask = alpha.point(lambda a: 255 if a > _CROP_ALPHA_FLOOR else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return img

    left, top, right, bottom = bbox
    width, height = img.size
    left = max(0, left - _CROP_PADDING)
    top = max(0, top - _CROP_PADDING)
    right = min(width, right + _CROP_PADDING)
    bottom = min(height, bottom + _CROP_PADDING)
    return img.crop((left, top, right, bottom))


def prepare_signature(src_path: str, out_path: str) -> str:
    """Process ``src_path`` into a transparent PNG written to ``out_path``.

    Returns ``out_path``. Raises ``ValueError`` if the source cannot be read as an
    image or contains no detectable signature.
    """
    try:
        with Image.open(src_path) as opened:
            img = ImageOps.exif_transpose(opened)
            img.load()
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read image: {src_path}") from exc

    if _has_real_transparency(img):
        result = _autocrop(img.convert("RGBA"))
        result.save(out_path, "PNG")
        return out_path

    rgb = img.convert("RGB")
    gray = rgb.convert("L")
    paper_level = _estimate_paper_level(gray)
    alpha = gray.point(_alpha_lut(paper_level))

    result = rgb.convert("RGBA")
    result.putalpha(alpha)

    if result.getchannel("A").getbbox() is None:
        raise ValueError("No signature detected in the image.")

    result = _autocrop(result)
    result.save(out_path, "PNG")
    return out_path
