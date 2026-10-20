import assert from "node:assert/strict";
import { test } from "node:test";

import { dayKey, groupByDay, linkHref } from "./audit.ts";

test("entries are grouped by day in Dushanbe time, newest first, order kept", () => {
  const now = new Date("2026-10-20T10:00:00Z");
  const items = [
    { id: 4, at: "2026-10-20T08:00:00Z" },
    { id: 3, at: "2026-10-19T20:30:00Z" }, // 01:30 on the 20th in Dushanbe (UTC+5)
    { id: 2, at: "2026-10-19T10:00:00Z" },
    { id: 1, at: "2026-10-10T10:00:00Z" },
  ];
  const groups = groupByDay(items, now);

  assert.deepEqual(
    groups.map((g) => [g.day, g.label, g.items.map((i) => i.id)]),
    [
      ["2026-10-20", "Сегодня", [4, 3]],
      ["2026-10-19", "Вчера", [2]],
      ["2026-10-10", "10 октября 2026 г.", [1]],
    ],
  );
  assert.equal(dayKey("2026-10-19T20:30:00Z"), "2026-10-20");
});

test("links: students and cohorts open their page, the rest a list, no link stays null", () => {
  assert.equal(linkHref({ entity: "student", id: "s1" }), "/students/s1");
  assert.equal(linkHref({ entity: "cohort", id: "c1" }), "/cohorts/c1");
  assert.equal(linkHref({ entity: "app_user", id: "u1" }), "/users");
  assert.equal(linkHref({ entity: "course", id: "x" }), "/rooms");
  assert.equal(linkHref(null), null);
});
