import assert from "node:assert/strict";
import { test } from "node:test";

import { compact, niceTicks, orDash, shortMonth } from "./reports.ts";

test("compact money", () => {
  assert.equal(compact(950), "950");
  assert.match(compact(12_500), /12,5 тыс\./);
  assert.match(compact(2_000_000), /2 млн/);
});

test("short month", () => assert.equal(shortMonth("2026-10-01"), "окт"));

test("a missing number is a dash, not zero", () => {
  assert.equal(
    orDash(null, (v) => v),
    "—",
  );
  assert.equal(
    orDash("0", (v) => `${v}!`),
    "0!",
  );
});

test("ticks cover the range including a negative profit", () => {
  const t = niceTicks(-300, 1000);

  assert.ok(t[0] <= -300 && t[t.length - 1] >= 1000);
  assert.ok(t.includes(0));
});

test("ticks of an all-zero chart", () => assert.ok(niceTicks(0, 0).length >= 2));
