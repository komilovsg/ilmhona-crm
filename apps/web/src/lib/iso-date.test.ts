import assert from "node:assert/strict";
import { test } from "node:test";

import { parseIso, toIso } from "./iso-date.ts";

test("a date round-trips through the picker value", () => {
  assert.equal(toIso(parseIso("2026-11-09")), "2026-11-09");
  assert.equal(toIso(parseIso("2026-01-05")), "2026-01-05");
});

test("a date with time round-trips", () => {
  assert.equal(toIso(parseIso("2026-11-09T16:05", true), true), "2026-11-09T16:05");
  assert.equal(toIso(parseIso("2026-11-09", true), true), "2026-11-09T00:00");
});

test("empty and malformed input is null, no value is empty string", () => {
  assert.equal(parseIso(""), null);
  assert.equal(parseIso("09.11.2026"), null);
  assert.equal(parseIso("2026-13-01"), null);
  assert.equal(toIso(null), "");
});
