import assert from "node:assert/strict";
import { test } from "node:test";

import { BLANK_LAYOUT, makeBlock, newId } from "./blocks.ts";
import { HISTORY_LIMIT, initialState, isDirty, reducer, reorder, withRect, type Action, type EditorState } from "./reducer.ts";
import type { Layer } from "./types.ts";

const run = (s: EditorState, ...actions: Action[]) => actions.reduce(reducer, s);
const rect = (id: string, x = 10, y = 10): Layer => ({ id, type: "rect", fill: "#ffffff", x_mm: x, y_mm: y, w_mm: 20, h_mm: 10, rotation: 0, locked: false });
const base = () => run(initialState(BLANK_LAYOUT), { type: "add", layers: [rect("rect-1"), rect("rect-2", 50, 50)] });

test("add selects the new layers and is one undo step", () => {
  const s = base();

  assert.deepEqual(s.selection, ["rect-1", "rect-2"]);
  assert.equal(s.layout.layers.length, 2);
  assert.equal(run(s, { type: "undo" }).layout.layers.length, 0);
  assert.equal(run(s, { type: "undo" }, { type: "redo" }).layout.layers.length, 2);
});

test("a live drag is one history step; an empty gesture leaves none", () => {
  let s = run(base(), { type: "select", ids: ["rect-1"] });
  const steps = s.past.length;

  s = run(s, { type: "begin" }, { type: "update", ids: ["rect-1"], fn: withRect({ x: 20, y: 20, w: 20, h: 10 }), live: true }, { type: "update", ids: ["rect-1"], fn: withRect({ x: 30, y: 25, w: 20, h: 10 }), live: true }, { type: "end" });
  assert.equal(s.past.length, steps + 1);
  assert.equal(s.layout.layers[0].x_mm, 30);
  assert.equal(run(s, { type: "undo" }).layout.layers[0].x_mm, 10);
  assert.equal(run(s, { type: "begin" }, { type: "end" }).past.length, steps + 1);
});

test("nudge moves unlocked selected layers, locked ones stay", () => {
  let s = run(base(), { type: "select", ids: ["rect-1", "rect-2"] });

  s = run(s, { type: "update", ids: ["rect-2"], fn: (l) => ({ ...l, locked: true }) }, { type: "nudge", dx: 1, dy: 0 });
  assert.equal(s.layout.layers[0].x_mm, 11);
  assert.equal(s.layout.layers[1].x_mm, 50);
  assert.equal(run(s, { type: "nudge", dx: 10, dy: -10 }).layout.layers[0].y_mm, 0);
});

test("duplicate gets a new unique id, offset, unlocked", () => {
  const s = run(base(), { type: "select", ids: ["rect-1"] }, { type: "update", ids: ["rect-1"], fn: (l) => ({ ...l, locked: true }) }, { type: "duplicate" });
  const ids = s.layout.layers.map((l) => l.id);

  assert.equal(new Set(ids).size, 3);
  assert.equal(s.layout.layers[2].x_mm, 15);
  assert.equal(s.layout.layers[2].locked, false);
  assert.deepEqual(s.selection, [s.layout.layers[2].id]);
});

test("delete removes the selection and clears it", () => {
  const s = run(base(), { type: "select", ids: ["rect-1"] }, { type: "delete" });

  assert.deepEqual(s.layout.layers.map((l) => l.id), ["rect-2"]);
  assert.deepEqual(s.selection, []);
});

test("z-order: front, back, up, down", () => {
  const l = [rect("a"), rect("b"), rect("c")];
  const ids = (x: Layer[]) => x.map((i) => i.id).join("");

  assert.equal(ids(reorder(l, "a", "front")), "bca");
  assert.equal(ids(reorder(l, "c", "back")), "cab");
  assert.equal(ids(reorder(l, "b", "up")), "acb");
  assert.equal(ids(reorder(l, "b", "down")), "bac");
  assert.equal(ids(reorder(l, "c", "up")), "abc");
});

test("history keeps at most the limit, newest steps", () => {
  let s = initialState(BLANK_LAYOUT);

  for (let i = 0; i < HISTORY_LIMIT + 30; i++) s = run(s, { type: "add", layers: [rect(`r-${i}`)] });
  assert.equal(s.past.length, HISTORY_LIMIT);
  for (let i = 0; i < HISTORY_LIMIT + 5; i++) s = run(s, { type: "undo" });
  assert.equal(s.layout.layers.length, 30);
});

test("a new edit clears redo; same coalesce key is one step", () => {
  let s = run(base(), { type: "undo" }, { type: "add", layers: [rect("rect-9")] });

  assert.equal(s.future.length, 0);
  s = run(s, { type: "update", ids: ["rect-9"], fn: (l) => ({ ...l, x_mm: 1 }), key: "k" }, { type: "update", ids: ["rect-9"], fn: (l) => ({ ...l, x_mm: 2 }), key: "k" });
  const before = s.past.length;

  assert.equal(run(s, { type: "undo" }).past.length, before - 1);
  assert.equal(run(s, { type: "undo" }).layout.layers.at(-1)?.x_mm, 10);
});

test("dirty flag follows content, not history", () => {
  const s = base();

  assert.equal(isDirty(s), true);
  assert.equal(isDirty(run(s, { type: "saved" })), false);
  assert.equal(isDirty(run(s, { type: "saved" }, { type: "update", ids: ["rect-1"], fn: (l) => ({ ...l, x_mm: 99 }) }, { type: "undo" })), false);
});

test("block factories give unique valid ids", () => {
  assert.equal(newId("text", ["text-1", "text-2"]), "text-3");
  const layers = [...makeBlock("director", [], { x: 100, y: 100 }), ...makeBlock("name", ["name-1"], { x: 100, y: 100 })];

  assert.equal(new Set(layers.map((l) => l.id)).size, layers.length);
  for (const l of layers) assert.match(l.id, /^[a-z0-9_-]{1,40}$/);
  const name = makeBlock("name", [], { x: 148.5, y: 105 })[0];

  assert.equal(name.type === "text" && name.content.filter((r) => "field" in r).length, 2);
  assert.equal(name.x_mm, 48.5);
});

test("adopt swaps in the server copy without a history step", () => {
  const s = base();
  const server = { ...s.layout, page: { width_mm: 297, height_mm: 210.0 } };
  const next = reducer(s, { type: "adopt", layout: server });

  assert.equal(next.past.length, s.past.length);
  assert.equal(isDirty(next), false);
});
