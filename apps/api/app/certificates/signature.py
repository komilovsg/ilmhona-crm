"""Signature and seal images: a photo of ink on paper (or a transparent PNG) becomes a clean
transparent PNG.

A photo has uneven light, so the paper level is estimated per area (the local maximum of a
shrunk copy, smoothed) and the ink is what is darker than that level: the darkness over the
paper becomes the alpha channel, the colour is one ink colour for the whole image. An image that
already has real transparency (a drawing from a canvas) keeps its alpha. The result is cropped
to the content with a small margin and shrunk to at most 1200 px wide.
"""

import io
from typing import Literal

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.certificates.errors import CERT_ASSET_INVALID
from app.core.errors import DomainError

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_OUT_WIDTH = 1200
WORK_SIDE = 1600
Ink = Literal["original", "blue", "black"]
INKS: tuple[str, ...] = ("original", "blue", "black")
BLUE = (16, 38, 120)
BLACK = (0, 0, 0)
FLOOR = 10  # darkness below this over the paper is noise, not ink


def _open(data: bytes) -> Image.Image:
    if len(data) > MAX_INPUT_BYTES:
        raise DomainError(CERT_ASSET_INVALID, reason="too_large")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("PNG", "JPEG"):
            raise DomainError(CERT_ASSET_INVALID, reason="type")
        if img.format == "JPEG":
            img.draft("RGB", (WORK_SIDE * 2, WORK_SIDE * 2))  # decode smaller: a phone photo is big
        img.load()
    except UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError:
        raise DomainError(CERT_ASSET_INVALID, reason="unreadable") from None
    return ImageOps.exif_transpose(img)


def _has_transparency(img: Image.Image) -> bool:
    if img.mode == "P":
        return "transparency" in img.info
    if img.mode in ("RGBA", "LA"):
        lowest = min(img.getchannel("A").tobytes())
        return lowest < 250
    return False


def _paper_alpha(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    """(rgb, alpha) of a photo: alpha is the darkness over the estimated paper level."""
    rgb = img.convert("RGB")
    rgb.thumbnail((WORK_SIDE, WORK_SIDE), Image.Resampling.LANCZOS)
    gray = rgb.convert("L").filter(ImageFilter.MedianFilter(3))
    small = gray.resize(
        (max(1, gray.width // 8), max(1, gray.height // 8)), Image.Resampling.BILINEAR
    )
    window = 2 * max(2, round(0.06 * max(small.size))) + 1
    paper = small.filter(ImageFilter.MaxFilter(window)).filter(ImageFilter.GaussianBlur(window / 3))
    paper = paper.resize(gray.size, Image.Resampling.BICUBIC)
    # darkness over the paper (clipped at 0), stretched so the strongest ink is opaque
    dark = ImageChops.subtract(paper, gray)
    hist = dark.histogram()
    total = sum(hist)
    cut, run, top = total * 0.002, 0, 255
    for level in range(255, -1, -1):
        run += hist[level]
        if run >= cut:
            top = level
            break
    strong = max(top * 0.7, FLOOR + 25)
    scale = 255 / (strong - FLOOR)
    lut = [0 if v <= FLOOR else min(255, round((v - FLOOR) * scale)) for v in range(256)]
    return rgb, dark.point(lut)


def _ink_colour(rgb: Image.Image, alpha: Image.Image) -> tuple[int, int, int]:
    """The mean colour of the solid ink pixels, a little darker (blending lightens the edges)."""
    solid = alpha.point(lambda v: 255 if v > 200 else 0)
    if solid.getbbox() is None:
        solid = alpha.point(lambda v: 255 if v > 100 else 0)
    r, g, b = (ImageStat.Stat(rgb.getchannel(i), solid).mean[0] for i in range(3))
    return (round(r * 0.85), round(g * 0.85), round(b * 0.85))


def clean(data: bytes, ink: str = "original") -> bytes:
    """PNG bytes of the cleaned image; 422 `cert_asset_invalid` for anything unusable."""
    if ink not in INKS:
        raise DomainError(CERT_ASSET_INVALID, reason="ink")
    img = _open(data)
    if _has_transparency(img):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        colour = None if ink == "original" else (BLUE if ink == "blue" else BLACK)
        rgb = rgba.convert("RGB")
    else:
        rgb, alpha = _paper_alpha(img)
        colour = (
            _ink_colour(rgb, alpha) if ink == "original" else (BLUE if ink == "blue" else BLACK)
        )
    if colour is not None:
        rgb = Image.new("RGB", rgb.size, colour)
    box = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    if box is None:
        raise DomainError(CERT_ASSET_INVALID, reason="empty")
    margin = max(4, round(0.03 * max(box[2] - box[0], box[3] - box[1])))
    box = (
        max(0, box[0] - margin),
        max(0, box[1] - margin),
        min(rgb.width, box[2] + margin),
        min(rgb.height, box[3] + margin),
    )
    out = rgb.crop(box)
    out.putalpha(alpha.crop(box))
    if out.width > MAX_OUT_WIDTH:
        out = out.resize(
            (MAX_OUT_WIDTH, max(1, round(out.height * MAX_OUT_WIDTH / out.width))),
            Image.Resampling.LANCZOS,
        )
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
