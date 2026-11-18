"""Fixtures for the certificate tests: a seed-like layout, tiny images, templates in the database."""

import io
from copy import deepcopy
from typing import Any

from PIL import Image

from app.core.db import sessionmaker
from app.models import CertAsset, CertTemplate, CertTemplateVersion

GENERAL = "general_ru"


def png(color: tuple[int, int, int] = (240, 230, 200), size: tuple[int, int] = (60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10" viewBox="0 0 20 10">'
    b'<rect width="20" height="10" fill="#eee"/></svg>'
)


def text_layer(id_: str = "name", *runs: dict[str, Any], **style: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "type": "text",
        "x_mm": 20,
        "y_mm": 80,
        "w_mm": 257,
        "h_mm": 20,
        "style": {
            "font": "Montserrat",
            "weight": 700,
            "size_pt": 36,
            "color": "#1a1a1a",
            "align": "center",
            "valign": "middle",
            **style,
        },
        "content": list(runs) or [{"field": "student.full_name"}],
    }


def layout(background: str | None = "bg.png", *layers: dict[str, Any]) -> dict[str, Any]:
    """A seed-like certificate: A4 landscape, background, name, course, date, number, QR."""
    return {
        "schema": 1,
        "page": {"width_mm": 297, "height_mm": 210},
        "background": {"asset": background} if background else None,
        "layers": list(layers)
        or [
            text_layer("name"),
            text_layer(
                "course",
                {"text": "прошёл(ла) курс «"},
                {"field": "course.name"},
                {"text": "»"},
                weight=400,
                size_pt=18,
                valign="top",
            ),  # fmt: skip
            {
                **text_layer(
                    "date",
                    {"field": "certificate.issued_date", "format": "d month yyyy"},
                    size_pt=12,
                ),
                "y_mm": 150,
                "h_mm": 10,
            },  # fmt: skip
            {
                **text_layer("number", {"field": "certificate.number"}, size_pt=10),
                "y_mm": 190,
                "h_mm": 8,
            },  # fmt: skip
            {
                "id": "rule",
                "type": "line",
                "x_mm": 60,
                "y_mm": 140,
                "w_mm": 177,
                "h_mm": 1,
                "color": "#999999",
            },  # fmt: skip
            {"id": "qr", "type": "qr", "x_mm": 250, "y_mm": 165, "w_mm": 30, "h_mm": 30},
        ],
    }


def with_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    return layout(None, *layers)


def changed(base: dict[str, Any], **over: Any) -> dict[str, Any]:
    out = deepcopy(base)
    out.update(over)
    return out


async def make_template(key: str = GENERAL, lay: dict[str, Any] | None = None) -> str:
    """A template with one published version (asset refs in `lay` are made real here)."""
    lay = deepcopy(lay if lay is not None else layout())
    async with sessionmaker() as db:
        if lay.get("background"):
            asset = CertAsset(
                kind="background", mime="image/png", data=png(), sha256=f"sha-{key}",
                size_bytes=1, width_px=60, height_px=40,
            )  # fmt: skip
            db.add(asset)
            await db.flush()
            lay["background"]["asset"] = str(asset.id)
        t = CertTemplate(key=key, name=f"Template {key}", draft=lay)
        db.add(t)
        await db.flush()
        db.add(CertTemplateVersion(template_id=t.id, version_no=1, layout=lay))
        await db.commit()
        return str(t.id)
