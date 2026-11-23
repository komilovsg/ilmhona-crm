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

test("the months of a period", async () => {
  const { monthsOfPeriod, periodTitle } = await import("./schedule-board.ts");

  assert.deepEqual(monthsOfPeriod("month", "2026-11-23"), [{ from: "2026-11-01", to: "2026-11-30", title: "Ноябрь 2026" }]);

  const half = monthsOfPeriod("half", "2026-11-23");

  assert.equal(half.length, 6);
  assert.deepEqual(half[5], { from: "2027-04-01", to: "2027-04-30", title: "Апрель 2027" });
  assert.equal(periodTitle("half", "2026-11-23"), "Ноябрь 2026 – Апрель 2027");

  const year = monthsOfPeriod("year", "2028-07-10");

  assert.equal(year.length, 12);
  assert.equal(year[0].from, "2028-01-01");
  assert.equal(year[1].to, "2028-02-29");
  assert.equal(periodTitle("year", "2028-07-10"), "2028");
});

test("a month is printed week by week", async () => {
  const { weekBands } = await import("./schedule-board.ts");
  const bands = weekBands("2026-11-01", "2026-11-30");

  // 1 November 2026 is a Sunday, the 30th a Monday
  assert.deepEqual(bands[0], ["2026-11-01"]);
  assert.equal(bands[1][0], "2026-11-02");
  assert.equal(bands[1].length, 7);
  assert.deepEqual(bands[bands.length - 1], ["2026-11-30"]);
  assert.equal(bands.flat().length, 30);
});

test("a step moves by the period", async () => {
  const { shiftDay } = await import("./schedule-board.ts");

  assert.equal(shiftDay("week", "2026-12-28", 1), "2027-01-04");
  assert.equal(shiftDay("month", "2026-01-31", 1), "2026-02-01");
  assert.equal(shiftDay("month", "2026-01-15", -1), "2025-12-01");
  assert.equal(shiftDay("half", "2026-11-23", 1), "2027-05-01");
  assert.equal(shiftDay("year", "2026-11-23", -1), "2025-01-01");
});
