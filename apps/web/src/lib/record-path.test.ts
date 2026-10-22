import assert from "node:assert/strict";
import { test } from "node:test";

import { isMissingStatus, recordApiPath } from "./record-path.ts";

test("only a student or cohort detail page maps to its API record", () => {
  assert.equal(recordApiPath("/students/abc"), "/api/v1/students/abc");
  assert.equal(recordApiPath("/cohorts/abc"), "/api/v1/cohorts/abc");
  assert.equal(recordApiPath("/students"), null);
  assert.equal(recordApiPath("/students/abc/x"), null);
  assert.equal(recordApiPath("/lessons/abc"), null);
});

test("missing means 404 or 422 only", () => {
  assert.deepEqual([404, 422, 401, 500, 200].map(isMissingStatus), [true, true, false, false, false]);
});
