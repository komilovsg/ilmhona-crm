"""A logo on a flat background is stored without it; other pictures are left alone."""

import io

import httpx
from PIL import Image, ImageDraw

from app.certificates.cutout import cut_background


def png(img: Image.Image, fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    img.save(out, fmt, quality=92)
    return out.getvalue()


def logo(ground: tuple[int, int, int], fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (400, 300), ground)
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 90, 280, 210), fill=(0, 90, 200))
    draw.ellipse((170, 120, 230, 180), fill=(230, 40, 40))
    return png(img, fmt)


def test_a_logo_on_white_loses_the_white_and_is_trimmed() -> None:
    cut = cut_background(logo((255, 255, 255)))
    assert cut is not None
    out = Image.open(io.BytesIO(cut))
    assert out.mode == "RGBA"
    # trimmed to the mark and a small margin
    assert 160 <= out.width <= 175 and 120 <= out.height <= 135
    assert out.getpixel((0, 0))[3] == 0
    r, g, b, a = out.getpixel((out.width // 5, out.height // 2))
    assert a == 255 and (r, g, b) == (0, 90, 200)
    r, g, b, a = out.getpixel((out.width // 2, out.height // 2))
    assert a == 255 and r > 200 and g < 70


def test_a_brand_colour_background_and_a_jpeg_work_too() -> None:
    cut = cut_background(logo((250, 240, 200), "JPEG"))
    assert cut is not None
    out = Image.open(io.BytesIO(cut))
    assert out.getpixel((1, 1))[3] == 0
    blue = out.getpixel((out.width // 5, out.height // 2))
    assert blue[3] == 255 and blue[2] > 170 and blue[0] < 40


def test_other_pictures_are_left_alone() -> None:
    transparent = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    ImageDraw.Draw(transparent).rectangle((10, 10, 40, 30), fill=(0, 0, 0, 255))
    assert cut_background(png(transparent)) is None
    # a photo: the border is not one colour
    photo = Image.linear_gradient("L").resize((200, 200)).convert("RGB")
    assert cut_background(png(photo)) is None
    # one flat colour and nothing on it
    assert cut_background(png(Image.new("RGB", (100, 100), (255, 255, 255)))) is None
    assert cut_background(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None


async def test_upload_cuts_only_when_asked(admin: httpx.AsyncClient) -> None:
    async def upload(fields: dict[str, str]) -> dict[str, object]:
        r = await admin.post(
            "/api/v1/cert-assets",
            data=fields,
            files={"file": ("logo.png", logo((255, 255, 255)), "image/png")},
        )
        assert r.status_code == 200, r.text
        return dict(r.json())

    kept = await upload({"kind": "image"})
    assert kept["cut"] is False and (kept["width_px"], kept["height_px"]) == (400, 300)
    cut = await upload({"kind": "image", "cut": "true"})
    assert cut["cut"] is True and int(str(cut["width_px"])) < 200
    # a background is a whole page: never cut
    assert (await upload({"kind": "background", "cut": "true"}))["cut"] is False
