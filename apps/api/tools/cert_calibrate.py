#!/usr/bin/env python3
# ruff: noqa: E731, UP031  (one-off measuring script: short run helpers read best as lambdas)
"""Measure the legacy certificate pages and emit layout JSON for the renderer.

Run (from repo root):
    uvx --with playwright python apps/api/tools/cert_calibrate.py [--old DIR] [key ...]

Steps per template: load the old page in headless Chromium with a fixed sample
student, measure every filled text element, write seed/<key>.json, save a
reference screenshot, re-render the new layout as plain HTML and report the
per-layer offset (mm) between old and new text boxes.
"""

from __future__ import annotations

import argparse
import functools
import html
import http.server
import json
import shutil
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
SEED = REPO / "apps/api/app/certificates/seed"
ASSETS = REPO / "import-data/certificates"
OLD_DEFAULT = Path("/Users/shakhron/Developer/cetificate-generation-ilmhona/certificate")
FONTS_CSS = "https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,400;0,500;0,600;0,700;0,800;0,900;1,400;1,700&display=swap"

GREY = "#3c3c3b"


def student(lang="ru", **kw):
    s = {
        "name": "Фарход",
        "lastname": "Каримов",
        "gender": "male",
        "programm": "JavaScript LVL 1",
        "instructor": "Азиз Умаров",
        "certificateId": "№ CERT-2026-0001",
        "date": " от 18.11.2026" if lang == "ru" else " on 18.11.2026",
        "camp": False,
        "certificateType": "general",
    }
    s.update(kw)
    return s


# runs helpers
T = lambda t: {"text": t}
F = lambda k, fmt=None: {"field": k, **({"format": fmt} if fmt else {})}
G = lambda m, f: {"gender": {"male": m, "female": f}}
DATE = F("certificate.issued_date", "dd.mm.yyyy")
NUM = F("certificate.number")

# layer spec: id, sel, mode ('el' | 'tail'), content, plus optional
#   align (override), w_to (right limit mm for left-aligned), w (mm explicit),
#   min_ratio (shrink-to-fit), bug_date (old page cuts last char of the date)
GENERAL_LAYERS = lambda ru: [
    dict(id="number", sel="#certificate_id", content=[T("№ "), NUM]),
    dict(id="date", sel="#date", content=[T("от " if ru else "on "), DATE]),
    dict(id="name", sel="#name", content=[F("student.first_name")], w_to=285, shrink=True),
    dict(id="surname", sel="#surname", content=[F("student.last_name")], w_to=285, shrink=True),
    dict(
        id="finished",
        sel="#finishedCourse",
        content=[G("окончил курс", "окончила курс")] if ru else [T("is awarded to")],
    ),
    dict(
        id="course_label",
        sel="#programm__placeholder",
        content=[T("по программе" if ru else "for successful completion")],
    ),
    dict(
        id="course", sel="#programm", mode="tail", content=[F("course.name")], w_to=285, shrink=True
    ),
    dict(id="instructor", sel="#instructor", content=[F("instructor.full_name")]),
]

PAIR_LAYERS = lambda finished, with_course: [  # kids index.html layout
    dict(id="number", sel="#certificate_id", content=[T("№ "), NUM]),
    dict(id="date", sel="#date", content=[T("от "), DATE]),
    dict(id="name", sel="#name", content=[F("student.first_name")], w_to=285, shrink=True),
    dict(id="surname", sel="#surname", content=[F("student.last_name")], w_to=285, shrink=True),
    dict(id="finished", sel="#finishedCourse", content=[G(*finished)]),
    dict(id="course", sel="#programm", content=[F("course.name")], w_to=285, shrink=True),
    dict(id="instructor", sel="#instructor", content=[F("instructor.full_name")]),
]

ID_LAYERS = lambda: [  # itp.html / kids.html layout
    dict(id="student_id", sel="#student-id", content=[T("ID "), NUM]),
    dict(
        id="name",
        sel="#name-surname",
        content=[F("student.first_name"), T(" "), F("student.last_name")],
        w_to=285,
        shrink=True,
    ),
    dict(id="finished", sel="#finished-course", content=[G("Окончил курс:", "Окончила курс:")]),
    dict(id="date", sel="#date", content=[T("| "), DATE], bug_date=True),
    dict(id="instructor", sel="#instructor", content=[F("instructor.full_name")]),
]

PROSKILLS_LAYERS = lambda with_instructor: (
    [
        dict(id="number_date", sel="#date", content=[T("№ "), NUM, T(" от "), DATE]),
        dict(id="name", sel="#name", content=[F("student.first_name")], w_to=285, shrink=True),
        dict(id="surname", sel="#surname", content=[F("student.last_name")], w_to=285, shrink=True),
        dict(
            id="finished",
            sel="#finishedCourse",
            content=[G("окончил специальный курс", "окончила специальный курс")],
        ),
        dict(id="course", sel="#programm", content=[F("course.name")], w_to=285, shrink=True),
    ]
    + (
        [dict(id="instructor", sel="#instructor", content=[F("instructor.full_name")])]
        if with_instructor
        else []
    )
)

FREELANCE_LAYERS = lambda: [
    dict(
        id="number_date",
        sel="#date",
        content=[T("№ "), NUM, T(" от "), DATE],
        align="center",
        w=120,
    ),
    dict(
        id="name",
        sel="#name",
        content=[F("student.first_name"), T(" "), F("student.last_name")],
        align="center",
        w=200,
        shrink=True,
    ),
    dict(
        id="finished",
        sel="#finishedCourse",
        content=[G("окончил курс", "окончила курс")],
        align="center",
        w=120,
    ),
]

TEMPLATES = [
    dict(
        key="general_ru",
        page="certificate/index.html",
        lang="ru",
        name="General RU",
        student=student("ru"),
        layers=GENERAL_LAYERS(True),
    ),
    dict(
        key="general_en",
        page="certificate/index-en.html",
        lang="en",
        name="General EN",
        student=student(
            "en",
            programm="JavaScript LVL 1",
            instructor="Aziz Umarov",
            name="Farhod",
            lastname="Karimov",
        ),
        layers=GENERAL_LAYERS(False),
    ),
    dict(
        key="itp",
        page="certificate/itp.html",
        lang="ru",
        name="Программирование с нуля",
        student=student("ru", programm="Программирование с нуля"),
        layers=ID_LAYERS(),
    ),
    dict(
        key="kids",
        page="certificatekids/index.html",
        lang="ru",
        name="Kids",
        student=student("ru", programm="Storytelling with Scratch", certificateType="kids"),
        layers=PAIR_LAYERS(("окончил курс", "окончила курс"), True),
    ),
    dict(
        key="kids_scratch",
        page="certificatekids/kids.html",
        lang="ru",
        name="Kids Scratch",
        student=student("ru", programm="Storytelling with Scratch", certificateType="kids"),
        layers=ID_LAYERS(),
    ),
    dict(
        key="proskills",
        page="certificateproskills/index.html",
        lang="ru",
        name="ProSkills",
        student=student("ru", programm="Product Management", certificateType="proskills"),
        layers=PROSKILLS_LAYERS(True),
    ),
    dict(
        key="proskills_islom",
        page="certificateproskills/index.html",
        lang="ru",
        name="ProSkills — Исломиддин Нуриддинов",
        student=student(
            "ru",
            programm="Product Management",
            certificateType="proskills",
            instructor="Исломиддин Нуриддинов",
        ),
        layers=PROSKILLS_LAYERS(False),
    ),
    dict(
        key="proskills_umed",
        page="certificateproskills/index.html",
        lang="ru",
        name="ProSkills — Умед Худойбердиев",
        student=student(
            "ru",
            programm="Product Management",
            certificateType="proskills",
            instructor="Умед Худойбердиев",
        ),
        layers=PROSKILLS_LAYERS(False),
    ),
    dict(
        key="freelance_jamshed",
        page="certificatefreelance/index.html",
        lang="ru",
        name="Freelance — Джамшед Бобоев",
        student=student(
            "ru", programm="Web 0", certificateType="freelance", instructor="Джамшед Бобоев"
        ),
        layers=FREELANCE_LAYERS(),
    ),
    dict(
        key="freelance_zarifkhon",
        page="certificatefreelance/index.html",
        lang="ru",
        name="Freelance — Зарифхон Олимов",
        student=student(
            "ru", programm="Web 0", certificateType="freelance", instructor="Зарифхон Олимов"
        ),
        layers=FREELANCE_LAYERS(),
    ),
]

MEASURE_JS = r"""
([sel, mode]) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  let nodes = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) nodes.push(w.currentNode);
  nodes = nodes.filter(n => n.textContent.trim());
  if (mode === 'tail') nodes = nodes.slice(-1);
  if (!nodes.length) return null;
  const first = nodes[0], last = nodes[nodes.length - 1];
  const r = document.createRange();
  r.setStart(first, first.textContent.search(/\S/));
  r.setEnd(last, last.textContent.replace(/\s+$/, '').length);
  const rects = [...r.getClientRects()].filter(q => q.width > 0);
  const lines = [...new Set(rects.map(q => Math.round(q.top)))].length;
  const cs = getComputedStyle(el);
  const eb = el.getBoundingClientRect();
  return {
    left: Math.min(...rects.map(q => q.left)), right: Math.max(...rects.map(q => q.right)),
    top: Math.min(...rects.map(q => q.top)), bottom: Math.max(...rects.map(q => q.bottom)),
    rh: rects[0].height, lines,
    text: r.toString(),
    el: {left: eb.left, top: eb.top, width: eb.width, height: eb.height},
    cs: {fs: parseFloat(cs.fontSize), fw: cs.fontWeight, fst: cs.fontStyle, color: cs.color,
         ta: cs.textAlign, lh: cs.lineHeight, ls: cs.letterSpacing, tt: cs.textTransform,
         ff: cs.fontFamily, opacity: cs.opacity}
  };
}
"""

CHECK_MEASURE_JS = r"""
(ids) => {
  const out = {};
  for (const id of ids) {
    const el = document.getElementById('L_' + id);
    const r = document.createRange(); r.selectNodeContents(el);
    const rects = [...r.getClientRects()].filter(q => q.width > 0);
    out[id] = {left: Math.min(...rects.map(q => q.left)), right: Math.max(...rects.map(q => q.right)),
               top: Math.min(...rects.map(q => q.top)), bottom: Math.max(...rects.map(q => q.bottom))};
  }
  const c = document.getElementById('page').getBoundingClientRect();
  return {boxes: out, page: {left: c.left, top: c.top, width: c.width, height: c.height}};
}
"""


def rgb_hex(c: str) -> str:
    import re

    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", c)
    return "#%02x%02x%02x" % tuple(int(x) for x in m.groups())


def r05(v):
    return round(v * 2) / 2


def r1(v):
    return round(v + 1e-9, 1)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root: Path):
    handler = functools.partial(Quiet, directory=str(root))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def fmt_date(fmt, d=(18, 11, 2026), lang="ru"):
    months_ru = [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    months_en = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    dd, mm, yy = d
    if fmt == "d month yyyy":
        return f"{dd} {months_ru[mm - 1]} {yy}"
    if fmt == "month d, yyyy":
        return f"{months_en[mm - 1]} {dd}, {yy}"
    return f"{dd:02d}.{mm:02d}.{yy}"


def sample_fields(st):
    return {
        "student.first_name": st["name"],
        "student.last_name": st["lastname"],
        "student.full_name": f"{st['name']} {st['lastname']}",
        "course.name": st["programm"],
        "instructor.full_name": st["instructor"],
        "certificate.number": st["certificateId"][2:],
    }


def run_text(content, st, bug_date=False):
    f = sample_fields(st)
    out = ""
    for run in content:
        if "text" in run:
            out += run["text"]
        elif "field" in run:
            if run["field"] == "certificate.issued_date":
                v = fmt_date(run.get("format"))
                if bug_date:
                    v = v[:-1]
                out += v
            else:
                out += f[run["field"]]
        else:
            out += run["gender"][st["gender"]]
    return out


def check_html(layout, st, bg_url, bug_ids):
    css = [
        f'@import url("{FONTS_CSS}");',
        "html,body{margin:0;padding:0}",
        "#page{position:relative;overflow:hidden;"
        f"width:{layout['page']['width_mm']}mm;height:{layout['page']['height_mm']}mm}}",
        "#page img{position:absolute;left:0;top:0;width:100%;height:100%}",
        ".L{position:absolute;white-space:pre-wrap;font-family:Montserrat,sans-serif;margin:0}",
    ]
    divs = []
    for ly in layout["layers"]:
        s = ly["style"]
        text = html.escape(run_text(ly["content"], st, ly["id"] in bug_ids))
        style = (
            f"left:{ly['x_mm']}mm;top:{ly['y_mm']}mm;width:{ly['w_mm']}mm;height:{ly['h_mm']}mm;"
            f"font-size:{s['size_pt']}pt;font-weight:{s['weight']};"
            f"font-style:{'italic' if s['italic'] else 'normal'};color:{s['color']};text-align:{s['align']};"
            f"line-height:{s['line_height']};letter-spacing:{s['letter_spacing_pt']}pt;"
            f"text-transform:{'uppercase' if s['uppercase'] else 'none'}"
        )
        divs.append(f'<div class="L" id="L_{ly["id"]}" style="{style}">{text}</div>')
    return (
        f'<!doctype html><meta charset="utf-8"><style>{"".join(css)}</style>'
        f'<div id="page"><img src="{bg_url}">{"".join(divs)}</div>'
    )


def build(pw_browser, base, tpl, old_root, args):
    key = tpl["key"]
    ctx = pw_browser.new_context(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"{base}/loginPage/login.html")  # same origin for localStorage
    page.evaluate(
        "([lang, st]) => {localStorage.setItem('lang', lang); localStorage.setItem('student', JSON.stringify(st));}",
        [tpl["lang"], tpl["student"]],
    )
    page.goto(f"{base}/{tpl['page']}", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_function(
        "(() => { const i = document.querySelector('img'); return i && i.complete && i.naturalWidth > 0; })()"
    )
    page.wait_for_timeout(300)
    img = page.evaluate(
        "(() => { const i = document.querySelector('img'); const r = i.getBoundingClientRect();"
        " return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height, nw: i.naturalWidth,"
        " nh: i.naturalHeight, src: i.getAttribute('src'), cur: i.currentSrc}; })()"
    )
    k = 297.0 / img["w"]
    page_h = r1(297.0 * img["h"] / img["w"])  # rect aspect also covers SVGs without intrinsic size
    ref = ASSETS / "reference" / f"{key}.png"
    page.screenshot(
        path=str(ref),
        full_page=True,
        clip={"x": img["x"], "y": img["y"], "width": img["w"], "height": img["h"]},
    )

    # background asset
    rel = img["cur"].replace(base + "/", "")
    from urllib.parse import unquote

    rel = unquote(rel)
    src_file = old_root / rel
    # old JS may differ in case from the file on disk (proSkills-Islom.png): use the real name
    src_file = [p for p in src_file.parent.iterdir() if p.name.lower() == src_file.name.lower()][0]
    asset_name = src_file.name
    if src_file.suffix == ".svg":
        asset_name = {
            "general.svg": "general_ru.png",
            "general_en.svg": "general_en.png",
            "kids.svg": "kids.png",
        }[src_file.name]
        shutil.copy(src_file, ASSETS / src_file.name)
        raster_svg(pw_browser, src_file, ASSETS / asset_name)
    else:
        shutil.copy(src_file, ASSETS / asset_name)

    layers = []
    old_boxes = {}
    for spec in tpl["layers"]:
        m = page.evaluate(MEASURE_JS, [spec["sel"], spec.get("mode", "el")])
        if m is None:
            print(f"  !! {key}: {spec['id']} not found/empty", file=sys.stderr)
            continue
        cs = m["cs"]
        fs = cs["fs"]
        size_pt = round(fs * k * 72 / 25.4, 1)
        lh = 1.2 if cs["lh"] == "normal" else float(cs["lh"].replace("px", "")) / fs
        lh = round(lh, 3)
        ls = 0 if cs["ls"] == "normal" else float(cs["ls"].replace("px", "")) * k * 72 / 25.4
        align = (
            spec.get("align")
            or {
                "start": "left",
                "left": "left",
                "center": "center",
                "right": "right",
                "end": "right",
            }[cs["ta"]]
        )
        line_px = lh * fs
        top_px = m["top"] - (line_px - m["rh"]) / 2 - img["y"]
        left_px = m["left"] - img["x"]
        right_px = m["right"] - img["x"]
        h_mm = m["lines"] * line_px * k
        text_w = (right_px - left_px) * k
        if align == "center":
            w_mm = spec.get("w") or max(m["el"]["width"] * k, text_w)
            x_mm = (left_px + right_px) / 2 * k - w_mm / 2
        else:
            x_mm = left_px * k
            if "w_to" in spec:
                w_mm = spec["w_to"] - x_mm
            else:
                w_mm = spec.get("w") or max(m["el"]["width"] * k, text_w)
            w_mm = max(w_mm, text_w + 0.5)
        mn = r05(0.6 * size_pt) if spec.get("shrink") else size_pt
        layers.append(
            {
                "id": spec["id"],
                "type": "text",
                "x_mm": r1(x_mm),
                "y_mm": r1(top_px * k),
                "w_mm": r1(w_mm),
                "h_mm": r1(h_mm),
                "rotation": 0,
                "locked": False,
                "style": {
                    "font": "Montserrat",
                    "weight": int(cs["fw"]),
                    "italic": cs["fst"] == "italic",
                    "size_pt": size_pt,
                    "min_size_pt": mn,
                    "color": rgb_hex(cs["color"]),
                    "align": align,
                    "valign": "top",
                    "line_height": lh,
                    "letter_spacing_pt": round(ls, 2),
                    "uppercase": cs["tt"] == "uppercase",
                },
                "content": spec["content"],
            }
        )
        old_boxes[spec["id"]] = {
            "left": (m["left"] - img["x"]) * k,
            "right": (m["right"] - img["x"]) * k,
            "top": (m["top"] - img["y"]) * k,
            "bottom": (m["bottom"] - img["y"]) * k,
            "text": m["text"],
        }
    layout = {
        "schema": 1,
        "page": {"width_mm": 297, "height_mm": page_h},
        "background": {"asset": asset_name},
        "layers": layers,
    }
    (SEED / f"{key}.json").write_text(
        json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # self-check: re-render as plain HTML and compare text boxes
    bug_ids = {s["id"] for s in tpl["layers"] if s.get("bug_date")}
    chk = ctx.new_page()
    chk_path = ASSETS / f"_check_{key}.html"
    chk_path.write_text(check_html(layout, tpl["student"], asset_name, bug_ids), encoding="utf-8")
    chk.goto(f"file://{chk_path}", wait_until="networkidle")
    chk.evaluate("document.fonts.ready")
    chk.wait_for_function(
        "(() => { const i = document.querySelector('img'); return i.complete && i.naturalWidth > 0; })()"
    )
    chk.wait_for_timeout(300)
    nm = chk.evaluate(CHECK_MEASURE_JS, [ly["id"] for ly in layers])
    pg = nm["page"]
    kn = 297.0 / pg["width"]
    new_png = ASSETS / "check" / f"_new_{key}.png"
    chk.set_viewport_size({"width": 1600, "height": 1200})
    # same pixel size as the reference: device scale = ref_px / css_px
    chk.close()
    ctx2 = pw_browser.new_context(
        viewport={"width": 1600, "height": 1200}, device_scale_factor=2 * img["w"] / pg["width"]
    )
    chk = ctx2.new_page()
    chk.goto(f"file://{chk_path}", wait_until="networkidle")
    chk.evaluate("document.fonts.ready")
    chk.wait_for_function(
        "(() => { const i = document.querySelector('img'); return i.complete && i.naturalWidth > 0; })()"
    )
    chk.wait_for_timeout(300)
    chk.locator("#page").screenshot(path=str(new_png))
    ctx2.close()
    chk_path.unlink()

    rows = {}
    for ly in layers:
        i = ly["id"]
        nb, ob = nm["boxes"][i], old_boxes[i]
        new = {
            e: ((nb[e] - pg["left"] if e in ("left", "right") else nb[e] - pg["top"]) * kn)
            for e in ("left", "right", "top", "bottom")
        }
        d = {e: new[e] - ob[e] for e in new}
        rows[i] = {
            "d": d,
            "max": max(abs(v) for v in d.values()),
            "max_lt": max(abs(d["left"]), abs(d["top"])),
        }
    side_by_side(ref, new_png, ASSETS / "check" / f"{key}.png")
    new_png.unlink()
    ctx.close()
    return {
        "key": key,
        "asset": asset_name,
        "page_mm": f"297x{page_h}",
        "layers": len(layers),
        "rows": rows,
        "img": img,
    }


def raster_svg(browser, svg: Path, out: Path, width_px=3508):
    ctx = browser.new_context(viewport={"width": width_px, "height": 2480}, device_scale_factor=1)
    p = ctx.new_page()
    p.set_content(
        f'<body style="margin:0"><img id="i" src="file://{svg}" style="display:block;width:{width_px}px"></body>'
    )
    p.wait_for_function("document.getElementById('i').complete")
    p.locator("#i").screenshot(path=str(out), omit_background=True)
    ctx.close()


def side_by_side(a: Path, b: Path, out: Path):
    import base64

    from playwright.sync_api import Error  # noqa: F401

    # difference overlay: old (red channel tint) vs new (cyan) via CSS blend, next to the old one
    A = base64.b64encode(a.read_bytes()).decode()
    B = base64.b64encode(b.read_bytes()).decode()
    out.with_suffix(".html").write_text(
        '<body style="margin:0;background:#fff"><div style="display:flex">'
        f'<img src="data:image/png;base64,{A}" style="width:50%">'
        '<div style="position:relative;width:50%;background:#fff">'
        f'<img src="data:image/png;base64,{A}" style="width:100%;display:block;filter:grayscale(1) sepia(1) hue-rotate(-50deg) saturate(8)">'
        f'<img src="data:image/png;base64,{B}" style="position:absolute;left:0;top:0;width:100%;mix-blend-mode:multiply;filter:grayscale(1) sepia(1) hue-rotate(150deg) saturate(8)">'
        "</div></div>",
        encoding="utf-8",
    )


def shoot_overlays(browser):
    for h in (ASSETS / "check").glob("*.html"):
        ctx = browser.new_context(viewport={"width": 2400, "height": 900}, device_scale_factor=1)
        p = ctx.new_page()
        p.goto(f"file://{h}")
        p.wait_for_timeout(200)
        p.screenshot(path=str(h.with_suffix(".png")), full_page=True)
        ctx.close()
        h.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--old", default=str(OLD_DEFAULT))
    args = ap.parse_args()
    old_root = Path(args.old)
    for d in (SEED, ASSETS / "reference", ASSETS / "check"):
        d.mkdir(parents=True, exist_ok=True)
    srv, port = serve(old_root)
    base = f"http://127.0.0.1:{port}"
    results = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for tpl in TEMPLATES:
            if args.keys and tpl["key"] not in args.keys:
                continue
            results.append(build(br, base, tpl, old_root, args))
        shoot_overlays(br)
        br.close()
    srv.shutdown()

    manifest = [
        {
            "key": t["key"],
            "name": t["name"],
            "lang": t["lang"] if t["key"] == "general_en" else "ru",
            "layout": f"{t['key']}.json",
        }
        for t in TEMPLATES
    ]
    if not args.keys:
        (SEED / "templates.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{'key':22} {'background':22} {'page':9} {'layers':6} {'max_off':8} {'max_left/top':12}")
    for r in results:
        mx = max(v["max"] for v in r["rows"].values())
        ml = max(v["max_lt"] for v in r["rows"].values())
        print(
            f"{r['key']:22} {r['asset']:22} {r['page_mm']:9} {r['layers']:6} {mx:8.2f} {ml:12.2f}"
        )
        if args.keys or mx > 1.0:
            for i, v in r["rows"].items():
                d = v["d"]
                print(
                    f"   {i:14} dL={d['left']:+.2f} dR={d['right']:+.2f} dT={d['top']:+.2f} dB={d['bottom']:+.2f}"
                )


if __name__ == "__main__":
    main()
