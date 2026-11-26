import assert from "node:assert/strict";
import { test } from "node:test";

import { inDays, lessonPhases, minutesOf, splitUnfilled, weekStart } from "./today.ts";
import type { LessonItem } from "./types.ts";

const lesson = (start: string, end: string, date = "2026-11-26"): LessonItem => ({
  lesson_id: `${date}${start}`,
  cohort_id: "c",
  cohort_code: "G-001",
  course_name: "Курс",
  room_name: "A",
  date,
  start,
  end,
  marked: 0,
  total: 5,
  instructor_id: null,
  instructor_name: null,
});

test("phases: past, now, next, later", () => {
  const ls = [lesson("08:00", "09:00"), lesson("10:00", "11:00"), lesson("12:00", "13:00"), lesson("14:00", "15:00")];
  assert.deepEqual(lessonPhases(ls, minutesOf("10:30")), ["past", "now", "next", "later"]);
  assert.deepEqual(lessonPhases(ls, minutesOf("07:00")), ["next", "later", "later", "later"]);
  assert.deepEqual(lessonPhases(ls, minutesOf("15:00")), ["past", "past", "past", "past"]);
  assert.deepEqual(lessonPhases(ls, minutesOf("09:00")), ["past", "next", "later", "later"]);
});

test("week start is Monday", () => {
  assert.equal(weekStart("2026-11-26"), "2026-11-23");
  assert.equal(weekStart("2026-11-23"), "2026-11-23");
  assert.equal(weekStart("2026-11-29"), "2026-11-23");
});

test("unfilled splits at Monday", () => {
  const r = splitUnfilled([lesson("08:00", "09:00", "2026-11-20"), lesson("08:00", "09:00", "2026-11-24")], "2026-11-26");
  assert.equal(r.week.length, 1);
  assert.equal(r.earlier.length, 1);
});

test("inDays wording", () => {
  assert.equal(inDays("2026-11-26", "2026-11-27"), "завтра");
  assert.equal(inDays("2026-11-26", "2026-11-29"), "через 3 дня");
  assert.equal(inDays("2026-11-26", "2026-12-07"), "через 11 дней");
  assert.equal(inDays("2026-11-26", "2026-12-17"), "через 21 день");
});
