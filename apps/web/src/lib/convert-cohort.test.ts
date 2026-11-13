import assert from "node:assert/strict";
import { test } from "node:test";

import { convertCohorts } from "./convert-cohort.ts";
import type { CohortRow } from "./types.ts";

const cohort = (id: string, course_id: string, status = "набор", enrolled = 1, capacity = 10) =>
  ({ id, course_id, status, capacity, fill: { enrolled, capacity } }) as CohortRow;

test("one open cohort of the lead's course is preselected", () => {
  const r = convertCohorts([cohort("a", "c2"), cohort("b", "c1")], "c1");

  assert.equal(r.auto, "b");
  assert.deepEqual(r.items.map((c) => c.id), ["b", "a"]);
});

test("several matches: none preselected, matches first", () => {
  const r = convertCohorts([cohort("a", "c2"), cohort("b", "c1"), cohort("c", "c1", "активный")], "c1");

  assert.equal(r.auto, null);
  assert.deepEqual(r.items.map((c) => c.id), ["b", "c", "a"]);
  assert.deepEqual([...r.match], ["b", "c"]);
});

test("full and finished cohorts do not count", () => {
  const r = convertCohorts([cohort("a", "c1", "набор", 10, 10), cohort("b", "c1", "завершён"), cohort("c", "c1")], "c1");

  assert.equal(r.auto, "c");
  assert.equal(r.items.length, 1);
});

test("lead without a course: nothing preselected", () => {
  assert.equal(convertCohorts([cohort("a", "c1")], null).auto, null);
});
