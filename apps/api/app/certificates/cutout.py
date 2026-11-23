"""A logo uploaded on a flat background becomes a logo on no background.

A logo usually arrives as a JPEG or a PNG on white (or on one brand colour). Put on a certificate
like that it shows as a box. When the border of the picture is one colour, that colour is the
background: every pixel gets the opacity that explains how far it is from it, its own colour is
recovered from under the mix, and the picture is trimmed to what is left. A picture that already
has transparency, or whose border is not one colour (a photo), is left alone.
"""

import io
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageMath, ImageStat

from app.certificates.signature import _has_transparency, _open
from app.core.errors import DomainError

MAX_SIDE = 2000
FLAT = 10.0  # the border counts as one colour up to this deviation, levels per channel
NOISE = 6  # levels a pixel may differ from the background and still be background (JPEG)
SOLID = 48  # opacity (of 255) from which a pixel is part of a shape, not of its soft edge
EMPTY, FULL = 0.003, 0.97  # share of inked pixels outside which nothing sensible was found


def _border(size: tuple[int, int]) -> Image.Image:
    w, h = size
    mask = Image.new("L", size, 255)
    if w > 8 and h > 8:
        mask.paste(0, (3, 3, w - 3, h - 3))
    return mask


def _unmix(level: int) -> Callable[[dict[str, Any]], Any]:
    """The channel `p` with the background `level` taken out from under the opacity `a`."""

    def run(env: dict[str, Any]) -> Any:
        opacity = env["max"](env["float"](env["a"]), 1)
        value = level + (env["float"](env["p"]) - level) * 255 / opacity
        return env["convert"](env["min"](env["max"](value, 0), 255), "L")

    return run


def cut_background(data: bytes) -> bytes | None:
    """PNG bytes without the flat background, or None when the picture is to be kept as it is."""
    try:
        img = _open(data)
    except DomainError:
        return None  # not a PNG or a JPEG: stored as uploaded
    if _has_transparency(img):
        return None
    rgb = img.convert("RGB")
    rgb.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    stat = ImageStat.Stat(rgb, _border(rgb.size))
    if max(stat.stddev) > FLAT:
        return None
    ground = [int(v) for v in stat.median]

    def opacity(level: int) -> list[int]:
        # the least opacity that can turn the background level into this one; the noise band is
        # taken off both the difference and its range, so a pure colour stays fully opaque
        out = []
        for v in range(256):
            reach = (255 - level if v > level else level) - NOISE
            out.append(min(255, round(255 * max(abs(v - level) - NOISE, 0) / max(reach, 1))))
        return out

    bands = [rgb.getchannel(i).point(opacity(ground[i])) for i in range(3)]
    alpha = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2])
    # that opacity is the least possible one: right on a soft edge, too low inside a solid shape
    # of a middle colour (a red on white would turn glassy). Inside a shape (clearly not the
    # background, and not on its rim) the picture is simply opaque
    core = alpha.point(lambda v: 255 if v > SOLID else 0).filter(ImageFilter.MinFilter(3))
    alpha = ImageChops.lighter(alpha, core)
    inked = ImageStat.Stat(alpha.point(lambda v: 255 if v > 24 else 0)).mean[0] / 255
    box = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    if box is None or not EMPTY <= inked <= FULL:
        return None
    # the colour that was mixed with the background: P = a·F + (1 − a)·B
    colour = [
        ImageMath.lambda_eval(_unmix(ground[i]), p=rgb.getchannel(i), a=alpha) for i in range(3)
    ]
    out = Image.merge("RGBA", [*colour, alpha])
    margin = max(2, round(0.02 * max(box[2] - box[0], box[3] - box[1])))
    out = out.crop(
        (
            max(box[0] - margin, 0),
            max(box[1] - margin, 0),
            min(box[2] + margin, out.width),
            min(box[3] + margin, out.height),
        )
    )
    buffer = io.BytesIO()
    out.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
