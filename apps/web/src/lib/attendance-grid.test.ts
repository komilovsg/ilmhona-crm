import assert from "node:assert/strict";
import { test } from "node:test";

import { arrowStep, cellMarkable, defaultMonth, keyMark, lessonsOfMonth, monthLabel, monthsOf, withMark } from "./attendance-grid.ts";

const L = (date: string, held: boolean, cancelled = false) => ({ date, held, cancelled });

test("months: sorted, unique, labelled", () => {
  const ls = [L("2026-10-02", false), L("2026-09-05", true), L("2026-09-12", true)];

  assert.deepEqual(monthsOf(ls), ["2026-09", "2026-10"]);
  assert.equal(monthLabel("2026-09"), "Сен 2026");
  assert.equal(lessonsOfMonth(ls, "2026-09").length, 2);
  assert.equal(lessonsOfMonth(ls, "all").length, 3);
});

test("default month: today's, else latest held, else all", () => {
  const ls = [L("2026-08-05", true), L("2026-09-05", true), L("2026-11-05", false)];

  assert.equal(defaultMonth(ls, "2026-09-20"), "2026-09");
  assert.equal(defaultMonth(ls, "2026-10-20"), "2026-09");
  assert.equal(defaultMonth([L("2026-11-05", false)], "2026-10-20"), "all");
  assert.equal(defaultMonth([], "2026-10-20"), "all");
});

test("keys 1 and 2 map to was / was not, others to nothing", () => {
  assert.equal(keyMark("1"), true);
  assert.equal(keyMark("2"), false);
  assert.equal(keyMark("3"), undefined);
  assert.equal(keyMark("Enter"), undefined);
});

test("arrow keys step between cells", () => {
  assert.deepEqual(arrowStep("ArrowLeft"), [0, -1]);
  assert.deepEqual(arrowStep("ArrowRight"), [0, 1]);
  assert.deepEqual(arrowStep("ArrowUp"), [-1, 0]);
  assert.deepEqual(arrowStep("ArrowDown"), [1, 0]);
  assert.equal(arrowStep("a"), undefined);
  assert.equal(arrowStep("toString"), undefined);
});

test("markable: writable lesson and enrolled by its date", () => {
  const lesson = { date: "2026-09-05", writable: true };

  assert.equal(cellMarkable(lesson, { enrolled_on: "2026-09-05" }), true);
  assert.equal(cellMarkable(lesson, { enrolled_on: "2026-09-06" }), false);
  assert.equal(cellMarkable({ ...lesson, writable: false }, { enrolled_on: "2026-01-01" }), false);
});

test("withMark sets and removes one cell", () => {
  const marks = { a: { present: true, reason: null } };

  assert.deepEqual(withMark(marks, "b", { present: false, reason: null }).b, { present: false, reason: null });
  assert.deepEqual(withMark(marks, "a", undefined), {});
});
