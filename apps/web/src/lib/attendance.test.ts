import assert from "node:assert/strict";
import { test } from "node:test";

import { lessonProgress, lessonsWord, markedLabel, markState, parseGrade, percentLabel } from "./attendance.ts";

test("percent and marked labels never pass an unmarked lesson off as attended (#12)", () => {
  assert.equal(percentLabel(null), "—");
  assert.equal(percentLabel(11.1), "11,1 %");
  assert.equal(percentLabel(100), "100 %");
  assert.equal(markedLabel(0, 14), "не отмечено");
  assert.equal(markedLabel(12, 14), "отмечено 12/14");
  assert.equal(markedLabel(0, 0), "нет студентов");
  assert.equal(markState(0, 5), "none");
  assert.equal(markState(3, 5), "partial");
  assert.equal(markState(5, 5), "done");
});

test("grade input accepts empty and 0..40 whole numbers only", () => {
  assert.deepEqual(parseGrade(""), { ok: true, value: null });
  assert.deepEqual(parseGrade(" 35 "), { ok: true, value: 35 });
  assert.deepEqual(parseGrade("0"), { ok: true, value: 0 });
  assert.deepEqual(parseGrade("40"), { ok: true, value: 40 });
  for (const bad of ["41", "-1", "3.5", "abc", "100"]) assert.deepEqual(parseGrade(bad), { ok: false });
});

test("Russian plural of lessons", () => {
  assert.equal(lessonsWord(1), "1 урок");
  assert.equal(lessonsWord(3), "3 урока");
  assert.equal(lessonsWord(5), "5 уроков");
  assert.equal(lessonsWord(11), "11 уроков");
  assert.equal(lessonsWord(21), "21 урок");
});

test("lesson progress counts a student only from the day of enrollment", () => {
  const grid = {
    lessons: [
      { id: "a", date: "2030-03-01" },
      { id: "b", date: "2030-03-05" },
    ],
    students: [
      { enrolled_at: "2030-02-01T05:00:00Z", marks: { a: {}, b: {} } },
      { enrolled_at: "2030-03-03T05:00:00Z", marks: {} },
    ],
  };

  assert.deepEqual(lessonProgress(grid, (iso) => iso.slice(0, 10)), {
    a: { marked: 1, total: 1 },
    b: { marked: 1, total: 2 },
  });
});
