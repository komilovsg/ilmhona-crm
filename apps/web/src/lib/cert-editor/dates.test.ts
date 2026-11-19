import assert from "node:assert/strict";
import { test } from "node:test";

import { formatDate } from "./dates.ts";
import { resolveRuns } from "./runs.ts";

test("dates follow the run's format", () => {
  assert.equal(formatDate("2026-11-18", null), "18.11.2026");
  assert.equal(formatDate("2026-03-02", "d month yyyy"), "2 марта 2026");
  assert.equal(formatDate("2026-03-02", "month d, yyyy"), "March 2, 2026");
  assert.equal(formatDate("not a date", "dd.mm.yyyy"), "not a date");
});

test("sample resolution formats only date fields", () => {
  const runs = [{ field: "certificate.issued_date", format: "d month yyyy" }, { text: " / " }, { field: "course.name" }];

  assert.equal(resolveRuns(runs, { "certificate.issued_date": "2026-11-18", "course.name": "Веб" }, null, new Set(["certificate.issued_date"])), "18 ноября 2026 / Веб");
});
