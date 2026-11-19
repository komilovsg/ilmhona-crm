// Signature pad maths: smoothing through quadratic curves and the crop box of the drawing.

export type Pt = { x: number; y: number };

export type Seg = { kind: "dot"; to: Pt } | { kind: "move"; to: Pt } | { kind: "quad"; ctrl: Pt; to: Pt } | { kind: "line"; to: Pt };

const mid = (a: Pt, b: Pt): Pt => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

/** One stroke -> canvas path segments: curves through the midpoints, the points being the control points. */
export function strokeSegments(points: Pt[]): Seg[] {
  if (points.length === 0) return [];
  if (points.length === 1) return [{ kind: "dot", to: points[0] }];
  if (points.length === 2) return [{ kind: "move", to: points[0] }, { kind: "line", to: points[1] }];
  const segs: Seg[] = [{ kind: "move", to: points[0] }];

  for (let i = 1; i < points.length - 1; i++) segs.push({ kind: "quad", ctrl: points[i], to: mid(points[i], points[i + 1]) });
  segs.push({ kind: "line", to: points[points.length - 1] });

  return segs;
}

/** The box around every point, grown by `pad`, kept inside the canvas; null for an empty drawing. */
export function cropBox(strokes: Pt[][], pad: number, width: number, height: number): { x: number; y: number; w: number; h: number } | null {
  const all = strokes.flat();

  if (!all.length) return null;
  const x0 = Math.max(0, Math.min(...all.map((p) => p.x)) - pad);
  const y0 = Math.max(0, Math.min(...all.map((p) => p.y)) - pad);
  const x1 = Math.min(width, Math.max(...all.map((p) => p.x)) + pad);
  const y1 = Math.min(height, Math.max(...all.map((p) => p.y)) + pad);

  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}
