// Pure geometry of the certificate canvas: mm <-> px, hit test, move, resize, snapping, nudging.

export type Rect = { x: number; y: number; w: number; h: number };
export type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export type Guide = { axis: "x" | "y"; pos: number };
export type Page = { width_mm: number; height_mm: number };

export const MIN_SIZE_MM = 2;
export const SNAP_MM = 1.5;
/** CSS px in one mm at 100 % zoom (96 dpi). */
export const PX_PER_MM = 96 / 25.4;
export const SAFE_MARGIN_MM = 5;
export const PT_MM = 25.4 / 72;

export const mmToPx = (mm: number, scale: number) => mm * scale;
export const pxToMm = (px: number, scale: number) => px / scale;
export const round1 = (n: number) => Math.round(n * 10) / 10;
export const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

/** Scale (px per mm) that fits the page into `availablePx` of width at the given zoom (1 = fit). */
export function fitScale(page: Page, availablePx: number, zoom = 1): number {
  return Math.max(0.2, (availablePx / page.width_mm) * zoom);
}

export function rectOf(l: { x_mm: number; y_mm: number; w_mm: number; h_mm: number }): Rect {
  return { x: l.x_mm, y: l.y_mm, w: l.w_mm, h: l.h_mm };
}

/** The topmost layer (last in draw order) under the point; a layer's rectangle ignores rotation. */
export function hitTest<T extends { x_mm: number; y_mm: number; w_mm: number; h_mm: number }>(
  layers: T[],
  xMm: number,
  yMm: number,
): T | null {
  for (let i = layers.length - 1; i >= 0; i--) {
    const r = rectOf(layers[i]);

    if (xMm >= r.x && xMm <= r.x + r.w && yMm >= r.y && yMm <= r.y + r.h) return layers[i];
  }

  return null;
}

export function isOutside(r: Rect, page: Page): boolean {
  return r.x < 0 || r.y < 0 || r.x + r.w > page.width_mm || r.y + r.h > page.height_mm;
}

export function moveRect(r: Rect, dx: number, dy: number): Rect {
  return { ...r, x: r.x + dx, y: r.y + dy };
}

/** Drag one handle by (dx, dy) mm: the opposite edge stays, the size never goes below `min`. */
export function resizeRect(r: Rect, handle: Handle, dx: number, dy: number, min = MIN_SIZE_MM): Rect {
  let left = r.x;
  let top = r.y;
  let right = r.x + r.w;
  let bottom = r.y + r.h;

  if (handle.includes("w")) left = Math.min(left + dx, right - min);
  if (handle.includes("e")) right = Math.max(right + dx, left + min);
  if (handle.includes("n")) top = Math.min(top + dy, bottom - min);
  if (handle.includes("s")) bottom = Math.max(bottom + dy, top + min);

  return { x: left, y: top, w: right - left, h: bottom - top };
}

/** Arrow key: 1 mm, with Shift 10 mm. */
export function nudgeDelta(key: string, shift: boolean): { dx: number; dy: number } | null {
  const step = shift ? 10 : 1;

  switch (key) {
    case "ArrowLeft":
      return { dx: -step, dy: 0 };
    case "ArrowRight":
      return { dx: step, dy: 0 };
    case "ArrowUp":
      return { dx: 0, dy: -step };
    case "ArrowDown":
      return { dx: 0, dy: step };
    default:
      return null;
  }
}

/** Snap targets on one axis: page edges and centre plus the edges and centres of the other layers. */
export function targetsOf(axis: "x" | "y", page: Page, others: Rect[]): number[] {
  const size = axis === "x" ? page.width_mm : page.height_mm;
  const out = [0, size / 2, size];

  for (const o of others) {
    const a = axis === "x" ? o.x : o.y;
    const s = axis === "x" ? o.w : o.h;

    out.push(a, a + s / 2, a + s);
  }

  return out;
}

/** The target nearest to `value` within `threshold`, or null. */
export function nearest(value: number, targets: number[], threshold: number): number | null {
  let best: number | null = null;
  let bestD = threshold + 1e-9;

  for (const t of targets) {
    const d = Math.abs(t - value);

    if (d < bestD) {
      best = t;
      bestD = d;
    }
  }

  return best;
}

/** Move snap: left / centre / right (top / middle / bottom) of the rect against the targets, else a 1 mm grid. */
export function snapMove(
  r: Rect,
  others: Rect[],
  page: Page,
  opts: { enabled: boolean; threshold?: number },
): { rect: Rect; guides: Guide[] } {
  if (!opts.enabled) return { rect: { ...r, x: round1(r.x), y: round1(r.y) }, guides: [] };
  const threshold = opts.threshold ?? SNAP_MM;
  const guides: Guide[] = [];
  const out = { ...r };

  for (const axis of ["x", "y"] as const) {
    const start = axis === "x" ? r.x : r.y;
    const size = axis === "x" ? r.w : r.h;
    const targets = targetsOf(axis, page, others);
    let shift: number | null = null;
    let guide = 0;

    for (const anchor of [0, size / 2, size]) {
      const t = nearest(start + anchor, targets, threshold);

      if (t !== null && (shift === null || Math.abs(t - (start + anchor)) < Math.abs(shift))) {
        shift = t - (start + anchor);
        guide = t;
      }
    }
    if (shift === null) out[axis] = Math.round(start);
    else {
      out[axis] = start + shift;
      guides.push({ axis, pos: guide });
    }
  }

  return { rect: out, guides };
}

/** Resize snap: only the edges the handle moves are snapped (targets or the 1 mm grid). */
export function snapResize(
  r: Rect,
  handle: Handle,
  others: Rect[],
  page: Page,
  opts: { enabled: boolean; threshold?: number; min?: number },
): { rect: Rect; guides: Guide[] } {
  const min = opts.min ?? MIN_SIZE_MM;

  if (!opts.enabled) return { rect: r, guides: [] };
  const threshold = opts.threshold ?? SNAP_MM;
  const guides: Guide[] = [];
  let left = r.x;
  let right = r.x + r.w;
  let top = r.y;
  let bottom = r.y + r.h;
  const edge = (axis: "x" | "y", value: number) => {
    const t = nearest(value, targetsOf(axis, page, others), threshold);

    if (t === null) return Math.round(value);
    guides.push({ axis, pos: t });

    return t;
  };

  if (handle.includes("w")) left = Math.min(edge("x", left), right - min);
  if (handle.includes("e")) right = Math.max(edge("x", right), left + min);
  if (handle.includes("n")) top = Math.min(edge("y", top), bottom - min);
  if (handle.includes("s")) bottom = Math.max(edge("y", bottom), top + min);

  return { rect: { x: left, y: top, w: right - left, h: bottom - top }, guides };
}
