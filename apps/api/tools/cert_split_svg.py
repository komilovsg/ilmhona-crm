#!/usr/bin/env python3
"""Split the three vector certificate backgrounds into separate, movable layers.

Run (from repo root):
    uvx --with playwright python apps/api/tools/cert_split_svg.py [key ...]

Per template (general_ru, general_en, kids): every design element of the background SVG goes to
`import-data/certificates/parts/<key>/<part>.svg` with its viewBox cropped to the real bounding
box (measured in headless Chromium, strokes included, clipped to the page). The baked director
name and title and the embedded signature and seal images are not kept: they become the
`dir_name`, `dir_title` text layers and the `dir_signature` / `seal` image layers.
`seed/<key>.json` is rewritten: no background, one image layer per part, the director layers,
then the text layers that were already there.
"""

from __future__ import annotations

import copy
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
SEED = REPO / "apps/api/app/certificates/seed"
ASSETS = REPO / "import-data/certificates"
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
SOURCES = {"general_ru": "general.svg", "general_en": "general_en.svg", "kids": "kids.svg"}
DIRECTOR_IDS = {
    "dir_name",
    "dir_title",
    "dir_signature",
    "seal",
    "director_name",
    "director_title",
    "signature",
}

# Baked director text (Montserrat curves) as live text: same style as the instructor layer.
# The offsets move the text box so the rendered glyphs land on the baked ones (mm).
NAME_STYLE = {"weight": 700, "size_pt": 15.7, "color": "#3c3c3b"}
TITLE_STYLE = {"weight": 400, "size_pt": 14.0, "color": "#3c3c3b"}
TEXT_OFFSET_MM = {
    "dir_name": (-0.15, -1.1),
    "dir_title": (0.0, -1.0),
}
TEXT_WIDTH_MM = 66.0

ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)

MEASURE_JS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('#part *')) {
    if (el.tagName === 'g' || el.tagName === 'defs' || el.tagName === 'style') continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const stroked = cs.stroke !== 'none' && parseFloat(cs.strokeWidth) > 0;
    const h = stroked ? parseFloat(cs.strokeWidth) / 2 : 0;
    out.push([r.left - h, r.top - h, r.right + h, r.bottom + h]);
  }
  return out;
}"""


def tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def parse_viewbox(root: ET.Element) -> tuple[float, float]:
    _, _, w, h = (float(v) for v in root.get("viewBox", "").split())
    return w, h


def pick(root: ET.Element) -> dict[str, list[ET.Element]]:
    """Name every design element of the source SVG."""
    holder = next(
        (c for c in root if tag(c) == "g" and c.get("id", "").startswith("_Слой_1")), root
    )
    items = list(holder)
    bg = next(c for c in items if c.get("id") == "BG")
    bg_parts = list(bg)
    after_bg = items[items.index(bg) + 1 :]
    title = next(c for c in after_bg if tag(c) == "g" and not c.get("id"))
    sign = next(c for c in items if c.get("id") == "_Подпись")
    logo_texts = list(next(c for c in items if c.get("id") == "_Лого"))
    images = [c for c in items if tag(c) == "image"]
    return {
        "frame": [bg_parts[0]],
        "panel": [bg_parts[1]],
        "panel_line": [bg_parts[2]],
        "dots": [next(c for c in items if c.get("id") == "_Кружки")],
        "logo": [next(c for c in items if c.get("id") == "Logo")],
        "title": [title],
        "_texts_logo": logo_texts,
        "_sign": list(sign),
        "_images": images,
    }


def part_svg(root: ET.Element, elements: list[ET.Element], view: str, wrap: bool = False) -> str:
    out = ET.Element(f"{{{SVG}}}svg", {"viewBox": view})
    for child in root:
        if tag(child) == "defs":
            out.append(copy.deepcopy(child))
    host = ET.SubElement(out, f"{{{SVG}}}g", {"id": "part"}) if wrap else out
    for el in elements:
        host.append(copy.deepcopy(el))
    return ET.tostring(out, encoding="unicode")


class Measurer:
    def __init__(self, page, root: ET.Element) -> None:  # noqa: ANN001
        self.page = page
        self.root = root
        self.vw, self.vh = parse_viewbox(root)

    def leaves(self, elements: list[ET.Element]) -> list[list[float]]:
        svg = part_svg(self.root, elements, f"0 0 {self.vw} {self.vh}", wrap=True)
        svg = svg.replace("<svg ", f'<svg width="{self.vw}" height="{self.vh}" ', 1)
        self.page.set_content(
            f"<!doctype html><body style='margin:0'>{svg}</body>", wait_until="load"
        )
        return self.page.evaluate(MEASURE_JS)

    def box(self, elements: list[ET.Element]) -> tuple[float, float, float, float]:
        return self.union(self.leaves(elements))

    def union(self, boxes: list[list[float]]) -> tuple[float, float, float, float]:
        x0 = max(0.0, min(b[0] for b in boxes))
        y0 = max(0.0, min(b[1] for b in boxes))
        x1 = min(self.vw, max(b[2] for b in boxes))
        y1 = min(self.vh, max(b[3] for b in boxes))
        return x0, y0, x1, y1


def lines(boxes: list[list[float]]) -> list[tuple[float, float, float, float]]:
    """Group glyph boxes into text lines by vertical overlap."""
    groups: list[list[list[float]]] = []
    for b in sorted(boxes, key=lambda b: b[1]):
        if groups and b[1] <= max(g[3] for g in groups[-1]):
            groups[-1].append(b)
        else:
            groups.append([b])
    return [
        (
            min(g[0] for g in grp),
            min(g[1] for g in grp),
            max(g[2] for g in grp),
            max(g[3] for g in grp),
        )
        for grp in groups
    ]


def image_geometry(el: ET.Element) -> tuple[float, float, float, float, float]:
    """(x, y, w, h, rotation) of an <image> with translate / rotate / scale: the unrotated box
    is turned around its centre, which is how the renderer rotates a layer."""
    t = el.get("transform", "")
    tx, ty = (float(v) for v in re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", t).groups())  # type: ignore[union-attr]
    rot = re.search(r"rotate\(([-\d.]+)\)", t)
    scale = re.search(r"scale\(([-\d.]+)\)", t)
    a = float(rot.group(1)) if rot else 0.0
    s = float(scale.group(1)) if scale else 1.0
    w, h = float(el.get("width", 0)) * s, float(el.get("height", 0)) * s
    r = math.radians(a)
    cx = tx + (w / 2) * math.cos(r) - (h / 2) * math.sin(r)
    cy = ty + (w / 2) * math.sin(r) + (h / 2) * math.cos(r)
    return cx - w / 2, cy - h / 2, w, h, a


def line_mm(style: dict) -> float:
    """Height of one text line (line_height 1.2) in mm, rounded up so the renderer keeps the full size."""
    return math.ceil(style["size_pt"] * 1.2 * 25.4 / 72 * 10) / 10


def mm(v: float) -> float:
    return round(v, 3)


def image_layer(
    layer_id: str, source: dict, box: tuple[float, float, float, float], rot: float = 0.0
):
    x, y, w, h = box
    return {
        "id": layer_id, "type": "image", "x_mm": mm(x), "y_mm": mm(y), "w_mm": mm(w),
        "h_mm": mm(h), "rotation": rot, "locked": False, "source": source, "fit": "contain",
    }  # fmt: skip


def text_layer(layer_id: str, x: float, y: float, w: float, h: float, style: dict, field: str):
    return {
        "id": layer_id, "type": "text", "x_mm": mm(x), "y_mm": mm(y), "w_mm": mm(w),
        "h_mm": mm(h), "rotation": 0, "locked": False,
        "style": {
            "font": "Montserrat", "weight": style["weight"], "italic": False,
            "size_pt": style["size_pt"], "min_size_pt": 10.0, "color": style["color"],
            "align": "left", "valign": "top", "line_height": 1.2, "letter_spacing_pt": 0,
            "uppercase": False,
        },
        "content": [{"field": field}],
    }  # fmt: skip


def split(key: str, page) -> dict:  # noqa: ANN001
    root = ET.parse(ASSETS / SOURCES[key]).getroot()
    layout_path = SEED / f"{key}.json"
    layout = json.loads(layout_path.read_text())
    vw, vh = parse_viewbox(root)
    sx, sy = layout["page"]["width_mm"] / vw, layout["page"]["height_mm"] / vh
    named = pick(root)
    m = Measurer(page, root)
    out_dir = ASSETS / "parts" / key
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.svg"):
        old.unlink()

    parts: list[tuple[str, list[ET.Element]]] = [
        (n, named[n]) for n in ("frame", "panel", "panel_line", "dots", "logo", "title")
    ]
    texts = sorted(named["_texts_logo"], key=lambda g: m.box([g])[1])
    parts += [("hashtag", [texts[0]]), ("website", [texts[1]])]
    signs = sorted(named["_sign"], key=lambda g: m.box([g])[0])
    director, caption = signs[0], signs[1]
    parts.append(("instructor_caption", [caption]))

    report: dict = {"parts": {}}
    new_layers: list[dict] = []
    for name, els in parts:
        x0, y0, x1, y1 = m.box(els)
        view = f"{x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f}"
        (out_dir / f"{name}.svg").write_text(part_svg(root, els, view) + "\n")
        box = (x0 * sx, y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy)
        new_layers.append(image_layer(name, {"asset": f"parts/{key}/{name}.svg"}, box))
        report["parts"][name] = [mm(v) for v in box]

    rows = lines(m.leaves([director]))
    assert len(rows) == 2, f"{key}: expected name + title lines, got {len(rows)}"
    for (lid, row), style in zip(
        (("dir_name", rows[0]), ("dir_title", rows[1])), (NAME_STYLE, TITLE_STYLE)
    ):
        dx, dy = TEXT_OFFSET_MM[lid]
        h = (row[3] - row[1]) * sy
        field = "company.director_name" if lid == "dir_name" else "company.director_title"
        new_layers.append(
            text_layer(
                lid, row[0] * sx + dx, row[1] * sy + dy, TEXT_WIDTH_MM, line_mm(style), style, field
            )
        )
        report["parts"][lid] = [mm(row[0] * sx), mm(row[1] * sy), mm((row[2] - row[0]) * sx), mm(h)]

    sig_el, seal_el = sorted(named["_images"], key=lambda e: float(e.get("width", 0)))
    for lid, el, source in (
        ("dir_signature", sig_el, {"signature": "director"}),
        ("seal", seal_el, {"company": "seal"}),
    ):
        x, y, w, h, rot = image_geometry(el)
        new_layers.append(image_layer(lid, source, (x * sx, y * sy, w * sx, h * sy), rot))
        report["parts"][lid] = [mm(x * sx), mm(y * sy), mm(w * sx), mm(h * sy), rot]

    keep = [
        layer for layer in layout["layers"]
        if layer["type"] == "text" and layer["id"] not in DIRECTOR_IDS
    ]  # fmt: skip
    # stacking as in the source: parts, baked director text, then signature and seal on top
    ordered = [layer for layer in new_layers if layer["id"] not in ("dir_signature", "seal")]
    ordered += [layer for layer in new_layers if layer["id"] in ("dir_signature", "seal")]
    layout["background"] = None
    layout["layers"] = ordered + keep
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str]) -> int:
    keys = argv or list(SOURCES)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for key in keys:
            report = split(key, page)
            print(key)
            for name, box in report["parts"].items():
                print(f"  {name:20s} {box}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
