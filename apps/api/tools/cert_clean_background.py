"""Remove the baked director and instructor blocks from the two freelance certificate backgrounds.

The backgrounds are smooth peach gradients. For each block the gradient under it is rebuilt
from a ring of design-free pixels around it: a 2D polynomial per colour channel is fitted on
the ring (pixels that deviate from the fit are dropped and the fit repeated), and the block
rectangle is filled with the model. The script prints, per block, the largest ring residual and
the largest step between the filled edge and the untouched pixels next to it.

    uv run --with numpy python tools/cert_clean_background.py [images_dir]

`images_dir` defaults to ../../import-data/certificates; results go to `<images_dir>/clean/`.
"""

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.certificates.signature import clean as clean_signature  # noqa: E402

# file -> blocks (name, x0, y0, x1, y1) in pixels of that file; "holdout" is an empty patch of
# background the same size as a block that is filled the same way and compared with the original,
# which measures the error of the method inside a patch (the real blocks have no ground truth)
BLOCKS: dict[str, list[tuple[str, int, int, int, int]]] = {
    "jamshed.png": [
        ("director", 720, 1620, 1430, 2190),
        ("instructor", 1750, 1810, 2390, 2190),
        ("holdout", 2530, 1690, 3170, 2190),
    ],
    "newDf.png": [
        ("director", 405, 836, 712, 1140),
        ("instructor", 930, 860, 1255, 1140),
        ("holdout", 1330, 860, 1640, 1140),
    ],
}
# ring widths (left, top, right, bottom) in pixels, kept clear of other design: the course text
# sits just above the blocks of newDf.png
RING = {"jamshed.png": (50, 50, 50, 50), "newDf.png": (50, 16, 50, 50)}
DEGREES = range(2, 11)
LIMIT = 2.0  # levels per channel: border step and holdout error must stay within it


def _basis(x: np.ndarray, y: np.ndarray, degree: int, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    u = (x - (x0 + x1) / 2) / ((x1 - x0) / 2)
    v = (y - (y0 + y1) / 2) / ((y1 - y0) / 2)
    return np.stack(
        [u**i * v**j for i in range(degree + 1) for j in range(degree + 1 - i)], axis=-1
    )


def _jacobi(grid: np.ndarray, steps: int) -> np.ndarray:
    """Laplace equation inside `grid`, its outer rows and columns held fixed."""
    for _ in range(steps):
        grid[1:-1, 1:-1] = 0.25 * (
            grid[:-2, 1:-1] + grid[2:, 1:-1] + grid[1:-1, :-2] + grid[1:-1, 2:]
        )
    return grid


def _edge(line: np.ndarray, size: int) -> np.ndarray:
    return np.array(Image.fromarray(line[None, :]).resize((size, 1), Image.Resampling.BILINEAR))[0]


def _harmonic(frame: np.ndarray) -> np.ndarray:
    """The smoothest surface (harmonic) inside a frame of boundary values, (h, w, 3), whose
    outer rows and columns are the frame. Solved on a coarse grid first, then refined."""
    h, w, _ = frame.shape
    out = np.empty_like(frame)
    k = max(1, min(h, w) // 40)
    ch, cw = max(3, h // k), max(3, w // k)
    for c in range(3):
        full = frame[..., c]
        small = np.array(Image.fromarray(full).resize((cw, ch), Image.Resampling.BILINEAR))
        small[0], small[-1] = _edge(full[0], cw), _edge(full[-1], cw)
        small[:, 0], small[:, -1] = _edge(full[:, 0], ch), _edge(full[:, -1], ch)
        small = _jacobi(small, 4000)
        grid = np.array(Image.fromarray(small).resize((w, h), Image.Resampling.BICUBIC))
        grid[0], grid[-1], grid[:, 0], grid[:, -1] = full[0], full[-1], full[:, 0], full[:, -1]
        out[..., c] = _jacobi(grid, 300)
    return out


def _fit(
    rgb: np.ndarray, rect: tuple[int, int, int, int], ring: tuple[int, int, int, int]
) -> tuple[np.ndarray, float, float]:
    """(filled block, max ring residual of the polynomial, max correction inside the block).

    The polynomial follows the gradient (the lowest degree whose ring residual is smallest
    while staying inside the ring's value range across the block, so it does not swing where
    it has no data); what it misses on the ring is a ripple of a few levels, carried into the
    block as the smoothest surface that matches the ring at the edge, so the fill meets the
    untouched pixels without a step."""
    x0, y0, x1, y1 = rect
    ex = (x0 - ring[0], y0 - ring[1], x1 + ring[2], y1 + ring[3])
    ys, xs = np.mgrid[ex[1] : ex[3], ex[0] : ex[2]]
    inner = (xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1)
    px, py = xs[~inner].astype(float), ys[~inner].astype(float)
    vals = rgb[ex[1] : ex[3], ex[0] : ex[2]][~inner].astype(float)
    lo, hi = vals.min(axis=0) - 3, vals.max(axis=0) + 3
    best: tuple[float, np.ndarray] | None = None
    for degree in DEGREES:
        a = _basis(px, py, degree, ex)
        use = np.ones(len(px), bool)
        for _ in range(8):
            coef = np.linalg.lstsq(a[use], vals[use], rcond=None)[0]
            res = np.abs(a @ coef - vals).max(axis=1)
            new = res <= 6.0
            if new.sum() == use.sum():
                break
            use = new
        model = _basis(xs.astype(float), ys.astype(float), degree, ex) @ coef
        block = model[y0 - ex[1] : y1 - ex[1], x0 - ex[0] : x1 - ex[0]]
        if (block < lo).any() or (block > hi).any():
            continue
        worst = float(res[use].max())
        if best is None or worst < best[0]:
            best = (worst, model)
    assert best is not None
    worst, model = best
    ripple = rgb[ex[1] : ex[3], ex[0] : ex[2]].astype(float) - model
    ox, oy = x0 - ex[0], y0 - ex[1]
    h, w = y1 - y0, x1 - x0
    frame = np.zeros((h, w, 3))
    depth = 3  # average the ripple over the 3 ring pixels next to the edge: less noise
    frame[0] = ripple[oy - depth : oy, ox : ox + w].mean(axis=0)
    frame[-1] = ripple[oy + h : oy + h + depth, ox : ox + w].mean(axis=0)
    frame[:, 0] = ripple[oy : oy + h, ox - depth : ox].mean(axis=1)
    frame[:, -1] = ripple[oy : oy + h, ox + w : ox + w + depth].mean(axis=1)
    surface = _harmonic(frame.astype(np.float32))
    filled = model[oy : oy + h, ox : ox + w] + surface
    return np.clip(np.rint(filled), 0, 255), worst, float(np.abs(surface).max())


def _step(out: np.ndarray, rect: tuple[int, int, int, int]) -> float:
    """Largest difference between the filled edge pixels and the outside pixels next to them."""
    x0, y0, x1, y1 = rect
    o = out.astype(float)
    pairs = [
        (o[y0:y1, x0], o[y0:y1, x0 - 1]),
        (o[y0:y1, x1 - 1], o[y0:y1, x1]),
        (o[y0, x0:x1], o[y0 - 1, x0:x1]),
        (o[y1 - 1, x0:x1], o[y1, x0:x1]),
    ]
    return max(float(np.abs(a - b).max()) for a, b in pairs)


def clean(src: Path, blocks: list[tuple[str, int, int, int, int]], dst: Path) -> bool:
    img = Image.open(src).convert("RGBA")
    arr = np.asarray(img).copy()
    ring = RING[src.name]
    ok = True
    for name, *box in blocks:
        rect = (box[0], box[1], box[2], box[3])
        model, worst, inside = _fit(arr[..., :3], rect, ring)
        x0, y0, x1, y1 = rect
        if name == "holdout":
            err = float(np.abs(model - arr[y0:y1, x0:x1, :3]).max())
            print(f"{src.name} holdout: max error inside the patch {err:.2f}")
            ok &= err <= LIMIT
            continue
        arr[y0:y1, x0:x1, :3] = model.astype(np.uint8)
        step = _step(arr[..., :3], rect)
        good = step <= LIMIT
        ok &= good
        print(
            f"{src.name} {name}: ring {ring}, polynomial residual on the ring max {worst:.2f}, "
            f"correction inside max {inside:.2f}, border step max {step:.2f} "
            f"{'ok' if good else 'FAIL'}"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(dst, optimize=True)
    return ok


# file -> (file name of the signature, name as printed under it, crop box in pixels). The box
# stops above the printed name: ink that runs into the letters cannot be told from them.
SIGNATURES: dict[str, tuple[str, str, tuple[int, int, int, int]]] = {
    "jamshed.png": ("boboev-jamshed.png", "Бобоев Джамшед", (1775, 1815, 2365, 2052)),
    "newDf.png": ("zarifkhon-olimov.png", "Зарифхон Олимов", (940, 870, 1245, 1068)),
}


def crop_signatures(root: Path) -> None:
    """The baked instructor signatures as transparent PNGs, plus the `instructors.json` list."""
    out = root / "instructors"
    out.mkdir(parents=True, exist_ok=True)
    listing = []
    for name, (file, full_name, box) in SIGNATURES.items():
        buf = io.BytesIO()
        Image.open(root / name).convert("RGB").crop(box).save(buf, format="PNG")
        (out / file).write_bytes(clean_signature(buf.getvalue()))
        listing.append({"full_name": full_name, "signature": f"instructors/{file}"})
        print(f"{name}: signature of {full_name} -> instructors/{file}")
    (root / "instructors.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../import-data/certificates")
    ok = True
    for name, blocks in BLOCKS.items():
        ok &= clean(root / name, blocks, root / "clean" / name)
    crop_signatures(root)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
