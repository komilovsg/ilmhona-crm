import assert from "node:assert/strict";
import { test } from "node:test";

import { dateStatusLabel, marksToWrite, resultText, skippedChips, type ImportCounts, type ImportDate } from "./journal-import.ts";

const counts: ImportCounts = {
  add: 10,
  same: 4,
  differ: 3,
  skip_future: 2,
  skip_before_enrollment: 0,
  skip_expelled: 1,
  skip_no_lesson: 0,
  unknown: 0,
  lessons_to_create: 1,
  matched: 5,
  unmatched: 1,
  missing: 0,
};

test("differing marks are written only when overwriting", () => {
  assert.equal(marksToWrite(counts, false), 10);
  assert.equal(marksToWrite(counts, true), 13);
});

test("only the non-zero skipped groups are listed", () => {
  assert.deepEqual(skippedChips(counts), ["будущие даты: 2", "отчисленные: 1"]);
});

test("date statuses and the result are worded in Russian", () => {
  const d: ImportDate = { col: 3, date: "2025-09-01", status: "conflict", lesson_id: null, reason: "аудитория занята потоком G-002" };

  assert.equal(dateStatusLabel(d), "аудитория занята потоком G-002");
  assert.equal(dateStatusLabel({ ...d, status: "create", reason: null }), "урок будет добавлен");
  assert.equal(resultText({ marks_added: 8, marks_overwritten: 1, lessons_created: 2 }), "Загружено отметок: 9, уроков добавлено: 2");
  assert.equal(resultText({ marks_added: 0, marks_overwritten: 0, lessons_created: 0 }), "Загружено отметок: 0");
});
