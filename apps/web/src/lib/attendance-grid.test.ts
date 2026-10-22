import assert from "node:assert/strict";
import { test } from "node:test";

import { cellMarkable, defaultMonth, lessonsOfMonth, monthLabel, monthsOf, nextPresent, withMark } from "./attendance-grid.ts";

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

test("mark cycle never goes back to unmarked", () => {
  assert.equal(nextPresent(undefined), true);
  assert.equal(nextPresent(true), false);
  assert.equal(nextPresent(false), true);
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
