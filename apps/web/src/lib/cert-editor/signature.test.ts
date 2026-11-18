import assert from "node:assert/strict";
import { test } from "node:test";

import { cropBox, strokeSegments } from "./signature.ts";

test("a tap is a dot, two points a line, more points smooth curves through midpoints", () => {
  assert.deepEqual(strokeSegments([{ x: 1, y: 1 }]), [{ kind: "dot", to: { x: 1, y: 1 } }]);
  assert.equal(strokeSegments([{ x: 0, y: 0 }, { x: 2, y: 2 }]).length, 2);
  const segs = strokeSegments([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 20, y: 10 }]);

  assert.deepEqual(segs[1], { kind: "quad", ctrl: { x: 10, y: 0 }, to: { x: 10, y: 5 } });
  assert.equal(segs.at(-1)?.kind, "line");
  assert.deepEqual(strokeSegments([]), []);
});

test("crop box pads the drawing and stays on the canvas", () => {
  assert.equal(cropBox([], 10, 100, 100), null);
  assert.deepEqual(cropBox([[{ x: 5, y: 40 }, { x: 60, y: 50 }]], 10, 100, 100), { x: 0, y: 30, w: 70, h: 30 });
});
