import assert from "node:assert/strict";
import { test } from "node:test";

import { boardDays, boardHours, clock, courseHue, linesOf, minutes, slotsOf } from "./schedule-board.ts";

test("the board shows 13:00–20:00 and widens around other lessons", () => {
  assert.deepEqual(boardHours([]), { from: 780, to: 1200 });
  assert.deepEqual(boardHours([{ start: "15:00", end: "16:30" }]), { from: 780, to: 1200 });
  assert.deepEqual(boardHours([{ start: "09:15", end: "10:45" }, { start: "19:00", end: "20:40" }]), {
    from: 540,
    to: 1260,
  });
  assert.equal(boardHours([{ start: "22:00", end: "00:00" }]).to, 1440);
});

test("half-hour rows", () => {
  const slots = slotsOf(780, 1200);

  assert.equal(slots.length, 14);
  assert.equal(clock(slots[0]), "13:00");
  assert.equal(clock(slots[13]), "19:30");
  assert.equal(minutes("17:05"), 1025);
});

test("a lesson takes the lines of its length", () => {
  // 17:00–18:30 from 13:00 = three half-hour rows starting at the ninth
  assert.deepEqual(linesOf({ start: "17:00", end: "18:30" }, 780), { line: 49, span: 18 });
  assert.deepEqual(linesOf({ start: "13:00", end: "13:30" }, 780), { line: 1, span: 6 });
  assert.deepEqual(linesOf({ start: "17:15", end: "18:00" }, 780), { line: 52, span: 9 });
  assert.equal(linesOf({ start: "18:00", end: "18:00" }, 780).span, 72);
});

test("a course keeps its colour", () => {
  assert.equal(courseHue("Python lvl 2"), courseHue("  python LVL 2 "));
  assert.notEqual(courseHue("Python lvl 2"), courseHue("Excel"));

  const hue = courseHue("Мобилография");

  assert.ok(hue >= 0 && hue < 360);
});

test("Sunday is printed only when it has lessons", () => {
  const week = ["2030-03-11", "2030-03-12", "2030-03-13", "2030-03-14", "2030-03-15", "2030-03-16", "2030-03-17"];

  assert.equal(boardDays(week, [{ date: "2030-03-16" }]).length, 6);
  assert.equal(boardDays(week, [{ date: "2030-03-17" }]).length, 7);
});
