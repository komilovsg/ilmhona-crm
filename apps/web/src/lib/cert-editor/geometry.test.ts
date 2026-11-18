import assert from "node:assert/strict";
import { test } from "node:test";

import { fitScale, hitTest, isOutside, mmToPx, moveRect, nudgeDelta, pxToMm, resizeRect, snapMove, snapResize, type Handle } from "./geometry.ts";

const PAGE = { width_mm: 297, height_mm: 210 };
const R = { x: 50, y: 40, w: 60, h: 20 };

test("mm and px convert both ways", () => {
  assert.equal(mmToPx(10, 3.78), 37.8);
  assert.ok(Math.abs(pxToMm(mmToPx(12.5, 4.2), 4.2) - 12.5) < 1e-9);
  assert.ok(Math.abs(fitScale(PAGE, 1188) - 4) < 1e-9);
  assert.ok(Math.abs(fitScale(PAGE, 1188, 0.5) - 2) < 1e-9);
});

test("move shifts the rect only", () => {
  assert.deepEqual(moveRect(R, 5, -3), { x: 55, y: 37, w: 60, h: 20 });
});

test("every handle keeps the opposite edge fixed", () => {
  const cases: [Handle, [number, number], { x: number; y: number; w: number; h: number }][] = [
    ["e", [10, 99], { x: 50, y: 40, w: 70, h: 20 }],
    ["w", [10, 99], { x: 60, y: 40, w: 50, h: 20 }],
    ["s", [99, 5], { x: 50, y: 40, w: 60, h: 25 }],
    ["n", [99, 5], { x: 50, y: 45, w: 60, h: 15 }],
    ["se", [10, 5], { x: 50, y: 40, w: 70, h: 25 }],
    ["nw", [10, 5], { x: 60, y: 45, w: 50, h: 15 }],
    ["ne", [10, 5], { x: 50, y: 45, w: 70, h: 15 }],
    ["sw", [10, 5], { x: 60, y: 40, w: 50, h: 25 }],
  ];

  for (const [h, [dx, dy], want] of cases) assert.deepEqual(resizeRect(R, h, dx, dy), want, h);
});

test("resize never goes below 2 mm and the far edge stays put", () => {
  assert.deepEqual(resizeRect(R, "e", -500, 0), { x: 50, y: 40, w: 2, h: 20 });
  assert.deepEqual(resizeRect(R, "w", 500, 0), { x: 108, y: 40, w: 2, h: 20 });
  assert.deepEqual(resizeRect(R, "n", 0, 500), { x: 50, y: 58, w: 60, h: 2 });
  assert.deepEqual(resizeRect(R, "s", 0, -500), { x: 50, y: 40, w: 60, h: 2 });
});

test("snap to page centre, edges and other layers; Alt (disabled) keeps the free position", () => {
  const centre = snapMove({ x: 118, y: 10, w: 60, h: 10 }, [], PAGE, { enabled: true });

  assert.equal(centre.rect.x, 118.5);
  assert.deepEqual(centre.guides.filter((g) => g.axis === "x"), [{ axis: "x", pos: 148.5 }]);

  const edge = snapMove({ x: 0.9, y: 50, w: 60, h: 10 }, [], PAGE, { enabled: true });

  assert.equal(edge.rect.x, 0);

  const other = snapMove({ x: 100, y: 120.8, w: 30, h: 10 }, [{ x: 10, y: 100, w: 50, h: 21 }], PAGE, { enabled: true });

  assert.equal(other.rect.y, 121);
  assert.ok(other.guides.some((g) => g.axis === "y" && g.pos === 121));

  const free = snapMove({ x: 118.23, y: 10.04, w: 60, h: 10 }, [], PAGE, { enabled: false });

  assert.deepEqual(free, { rect: { x: 118.2, y: 10, w: 60, h: 10 }, guides: [] });
});

test("without a target nearby the position goes to the 1 mm grid", () => {
  const { rect, guides } = snapMove({ x: 30.4, y: 70.6, w: 31, h: 11 }, [], PAGE, { enabled: true });

  assert.deepEqual([rect.x, rect.y], [30, 71]);
  assert.deepEqual(guides, []);
});

test("resize snaps only the moving edge", () => {
  const r = snapResize({ x: 50, y: 40, w: 98.2, h: 20 }, "e", [], PAGE, { enabled: true });

  assert.equal(r.rect.x, 50);
  assert.equal(r.rect.x + r.rect.w, 148.5);
  assert.deepEqual(r.rect.y, 40);
  assert.deepEqual(snapResize({ x: 50, y: 40, w: 98.2, h: 20 }, "e", [], PAGE, { enabled: false }).rect.w, 98.2);
  assert.ok(snapResize({ x: 50, y: 40, w: 1.2, h: 20 }, "e", [], PAGE, { enabled: true }).rect.w >= 2);
});

test("arrow keys nudge 1 mm, Shift 10 mm", () => {
  assert.deepEqual(nudgeDelta("ArrowLeft", false), { dx: -1, dy: 0 });
  assert.deepEqual(nudgeDelta("ArrowDown", true), { dx: 0, dy: 10 });
  assert.equal(nudgeDelta("a", false), null);
});

test("hit test takes the topmost layer; outside detection", () => {
  const layers = [
    { id: "a", x_mm: 0, y_mm: 0, w_mm: 100, h_mm: 100 },
    { id: "b", x_mm: 10, y_mm: 10, w_mm: 20, h_mm: 20 },
  ];

  assert.equal(hitTest(layers, 15, 15)?.id, "b");
  assert.equal(hitTest(layers, 80, 80)?.id, "a");
  assert.equal(hitTest(layers, 150, 150), null);
  assert.equal(isOutside({ x: 290, y: 0, w: 10, h: 5 }, PAGE), true);
  assert.equal(isOutside({ x: 10, y: 10, w: 10, h: 5 }, PAGE), false);
});
