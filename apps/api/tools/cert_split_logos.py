"""Lift the logos baked into the raster certificate backgrounds into images of their own.

For every logo box the background under it is rebuilt the way `cert_clean_background` does it
(a polynomial fitted on a ring of design-free pixels around the box). The logo is what differs
from that background: its colour and opacity are recovered per pixel (colour-to-alpha against
the rebuilt background), trimmed to its ink and saved as a transparent PNG; the background is
saved without it. The seed layouts then get one image layer per logo at the place it was cut
from, so a certificate renders as before, but the logo can be moved, resized or replaced.

    uv run --with numpy python tools/cert_split_logos.py [images_dir] [--write-layouts]

`images_dir` defaults to ../../import-data/certificates. Backgrounds go to `<images_dir>/clean/`,
logos to `<images_dir>/logos/`. Prints, per logo, the border step of the fill and the layer.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cert_clean_background import _fit, _step  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "app" / "certificates" / "seed"
PAGE_MM = 297.0
INK = 0.06  # opacity from which a pixel counts as the logo
PAD = 6  # px of margin kept around the ink
NOISE = 4.0  # levels per channel the rebuilt background may be off

# A polynomial cannot follow an edge of the background. A box named "…|columns" lies beside one:
# every column is drawn between the clean pixels just above and just below the box. A box named
# "…|sides" has a vertical edge running through it: the edge is found in the rows above the box,
# and every row takes the colour left of the box up to the edge and the colour right of it after.
# Such a fill is right to a pixel or two along the edges, which leaves hairlines in the lifted
# logo; "…|sides=<logo>" therefore takes the artwork from another file's logo (the same mark,
# cut from an even background) and only its place and size from this box.
# file -> (layout files, ring width, boxes). A box (name, x0, y0, x1, y1) in pixels of the file
# is generous: the logo is trimmed to its ink. A box named with "+" holds several logos in a row
# and is cut where a gap wider than 1.5 % of the page separates them.
JOBS: dict[str, tuple[list[str], int, list[tuple[str, int, int, int, int]]]] = {
    "itp.png": (["itp.json"], 12, [("intel+ilmhona", 181, 2024, 1086, 2212)]),
    "scratch.png": (["kids_scratch.json"], 12, [("intel+ilmhona", 188, 2107, 1140, 2303)]),
    "certificate.png": (["proskills.json"], 20, [("ilmhona", 560, 330, 1020, 830)]),
    "proskills-islom.png": (["proskills_islom.json"], 20, [("ilmhona", 560, 330, 1020, 830)]),
    "proskills-umed.png": (["proskills_umed.json"], 20, [("ilmhona", 560, 330, 1020, 830)]),
    "jamshed.png": (
        ["freelance_jamshed.json"],
        40,
        [
            ("ministry", 905, 238, 1276, 457),
            ("unicef", 1610, 257, 1929, 438),
            ("ilmhona|columns", 2225, 235, 2505, 470),
        ],
    ),
    "newDf.png": (
        ["freelance_zarifkhon.json"],
        20,
        [
            ("ministry", 384, 124, 565, 238),
            ("eu", 709, 129, 833, 238),
            ("unicef", 967, 139, 1130, 228),
            ("ilmhona|sides=jamshed_ilmhona", 1258, 124, 1380, 243),
        ],
    ),
}


def lift(crop: np.ndarray, ground: np.ndarray) -> np.ndarray:
    """RGBA of what lies over `ground` in `crop` (both RGB, float): colour-to-alpha per pixel."""
    # a few levels of difference are the fill's own error, not ink: on a near-white ground one
    # level is already several percent of opacity
    over = np.maximum(np.abs(crop - ground) - NOISE, 0.0)
    up = np.where(crop > ground, over / np.maximum(255.0 - ground, 1e-6), 0.0)
    down = np.where(crop < ground, over / np.maximum(ground, 1e-6), 0.0)
    alpha = np.clip(np.maximum(up, down).max(axis=-1), 0.0, 1.0)
    alpha[alpha < 0.02] = 0.0
    safe = np.maximum(alpha, 1e-6)[..., None]
    colour = np.clip((crop - (1.0 - safe) * ground) / safe, 0, 255)
    return np.dstack([np.rint(colour), np.rint(alpha * 255)]).astype(np.uint8)


def columns(rgb: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    """The box filled column by column, from the rows above it to the rows below it."""
    x0, y0, x1, y1 = rect
    top = np.median(rgb[y0 - 6 : y0 - 1, x0:x1].astype(float), axis=0)
    bottom = np.median(rgb[y1 + 1 : y1 + 6, x0:x1].astype(float), axis=0)
    t = (np.arange(y1 - y0) + 0.5)[:, None, None] / (y1 - y0)
    return np.rint(top[None] * (1 - t) + bottom[None] * t)


def sides(rgb: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    """The box filled row by row from its left and right neighbours, split at the vertical edge."""
    x0, y0, x1, y1 = rect
    above = np.median(rgb[y0 - 6 : y0 - 1, x0:x1].astype(float), axis=0)
    edge = int(np.abs(np.diff(above, axis=0)).sum(axis=-1).argmax()) + 1
    left = np.median(rgb[y0:y1, x0 - 6 : x0 - 1].astype(float), axis=1)
    right = np.median(rgb[y0:y1, x1 + 1 : x1 + 6].astype(float), axis=1)
    out = np.repeat(right[:, None, :], x1 - x0, axis=1)
    out[:, :edge] = left[:, None, :]
    # a slanted edge may cut the lower right corner: it is where the column right of the box and
    # the row below it change colour. Rows under that point took the colour beyond the slant
    # from their right neighbour; between the vertical edge and the slant the colour is still
    # the one above the box
    below = np.median(rgb[y1 + 1 : y1 + 6, x0:x1].astype(float), axis=0)
    jump_y = np.abs(np.diff(right, axis=0)).sum(axis=-1)
    jump_x = np.abs(np.diff(below[edge:], axis=0)).sum(axis=-1)
    if jump_y.max() > 12 and jump_x.size and jump_x.max() > 12:
        w, h = x1 - x0, y1 - y0
        ya, xb = int(jump_y.argmax()) + 1, edge + int(jump_x.argmax()) + 1
        ys, xs = np.mgrid[0:h, 0:w]
        inside = ((xb - w) * (ys - ya) - (h - ya) * (xs - w) > 0) & (xs >= edge)
        out[inside] = np.repeat(above[None], h, axis=0)[inside]
    return np.rint(out)


def pieces(rgba: np.ndarray, gap: int) -> list[tuple[int, int, int, int]]:
    """Ink boxes (x0, y0, x1, y1) inside `rgba`, split at empty column runs wider than `gap`."""
    ink = rgba[..., 3] >= INK * 255
    cols = np.flatnonzero(ink.any(axis=0))
    if cols.size == 0:
        return []
    out = []
    start = prev = int(cols[0])
    for c in [*map(int, cols[1:]), None]:
        if c is None or c - prev > gap:
            rows = np.flatnonzero(ink[:, start : prev + 1].any(axis=1))
            out.append((start, int(rows[0]), prev + 1, int(rows[-1]) + 1))
            start = c if c is not None else start
        prev = c if c is not None else prev
    return out


def solid(rgba: np.ndarray) -> tuple[int, int, int, int]:
    """The box (x0, y0, x1, y1) of the fully inked pixels: the mark without its soft edge."""
    ys, xs = np.nonzero(rgba[..., 3] >= 0.6 * 255)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def split(root: Path, name: str) -> tuple[bool, list[dict[str, object]]]:
    _layouts, ring_px, boxes = JOBS[name]
    cleaned = root / "clean" / name
    # the freelance backgrounds are already cleaned of the signature blocks: start from that
    src = cleaned if cleaned.exists() and name in ("jamshed.png", "newDf.png") else root / name
    arr = np.asarray(Image.open(src).convert("RGBA")).copy()
    original = arr[..., :3].astype(float).copy()
    width = arr.shape[1]
    mm = PAGE_MM / width
    ring = (ring_px, ring_px, ring_px, ring_px)
    layers: list[dict[str, object]] = []
    ok = True
    for label, x0, y0, x1, y1 in boxes:
        rect = (x0, y0, x1, y1)
        label, _, mode = label.partition("|")
        mode, _, donor = mode.partition("=")
        if mode:
            model, worst = (columns if mode == "columns" else sides)(arr[..., :3], rect), 0.0
        else:
            model, worst, _inside = _fit(arr[..., :3], rect, ring)
        rgba = lift(original[y0:y1, x0:x1], model.astype(float))
        arr[y0:y1, x0:x1, :3] = model.astype(np.uint8)
        step = _step(arr[..., :3], rect)
        # an edge-following fill meets its border to a pixel, not to a level: looked at by eye
        good = step <= 3.0 or mode == "sides"
        ok &= good
        names = label.split("+")
        found = pieces(rgba, max(8, round(width * 0.015)) if len(names) > 1 else 10**6)
        if len(found) != len(names):
            print(f"{name} {label}: expected {len(names)} logos, found {len(found)} FAIL")
            ok = False
            continue
        for logo, (a, b, c, d) in zip(names, found, strict=True):
            file = f"logos/{Path(name).stem}_{logo}.png"
            (root / "logos").mkdir(exist_ok=True)
            if donor:
                a, b, c, d = solid(rgba)
                art = Image.open(root / "logos" / f"{donor}.png")
                art = art.crop(solid(np.asarray(art))).resize(
                    (c - a, d - b), Image.Resampling.LANCZOS
                )
                art.save(root / file, optimize=True)
            else:
                a, b = max(a - PAD, 0), max(b - PAD, 0)
                c, d = min(c + PAD, x1 - x0), min(d + PAD, y1 - y0)
                Image.fromarray(rgba[b:d, a:c], "RGBA").save(root / file, optimize=True)
            layer = {
                "id": f"logo_{logo}",
                "type": "image",
                "x_mm": round((x0 + a) * mm, 2),
                "y_mm": round((y0 + b) * mm, 2),
                "w_mm": round((c - a) * mm, 2),
                "h_mm": round((d - b) * mm, 2),
                "rotation": 0,
                "locked": False,
                "source": {"asset": file},
                "fit": "contain",
            }
            layers.append(layer)
            print(
                f"{name} {logo}: ring residual {worst:.2f}, border step {step:.2f} "
                f"{'ok' if good else 'FAIL'}; {layer['w_mm']}x{layer['h_mm']} mm at "
                f"({layer['x_mm']}, {layer['y_mm']})"
            )
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(cleaned, optimize=True)
    return ok, layers


def write_layout(file: str, background: str, layers: list[dict[str, object]]) -> None:
    path = SEED / file
    layout = json.loads(path.read_text(encoding="utf-8"))
    layout["background"] = {"asset": f"clean/{background}"}
    kept = [x for x in layout["layers"] if not str(x["id"]).startswith("logo_")]
    layout["layers"] = [*layers, *kept]  # under everything else, as they were in the picture
    path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0]) if args else Path("../../import-data/certificates")
    ok = True
    for name, (layouts, _ring, _boxes) in JOBS.items():
        good, layers = split(root, name)
        ok &= good
        if good and "--write-layouts" in sys.argv:
            for file in layouts:
                write_layout(file, name, layers)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
