import assert from "node:assert/strict";
import { test } from "node:test";

import { analyticsQuery, dayMonth, periodFromQuery, leftLine, pct, periodLabel, retentionLine, share, statusLabel, weekRange } from "./analytics.ts";

test("status always has words, never colour alone", () => {
  assert.equal(statusLabel("ok"), "в норме");
  assert.equal(statusLabel("below"), "ниже цели");
  assert.equal(statusLabel(null), "нет данных");
});

test("retention line and who left", () => {
  const r = { started: 20, now: 17, left: { expelled: 2, stopped: 1 }, late_joined: 0, percent: 85, target: 85, status: "ok" as const };

  assert.equal(retentionLine(r), "Начали 20 → сейчас 17 · 85 %");
  assert.equal(retentionLine({ ...r, percent: 66.7 }), "Начали 20 → сейчас 17 · 66,7 %");
  assert.equal(retentionLine({ ...r, started: 0, percent: null }), "Начали 0 → сейчас 17 · —");
  assert.equal(retentionLine({ ...r, late_joined: 3 }), "Начали 20 → сейчас 17 · 85 % · присоединились позже: 3");
  assert.equal(leftLine(r.left), "ушли: отчислено 2, перестали ходить 1");
  assert.equal(leftLine({ expelled: 0, stopped: 0 }), null);
  assert.equal(pct(null), "—");
});

test("week labels and axis share", () => {
  assert.equal(dayMonth("2026-11-09"), "09.11");
  assert.equal(weekRange({ week_start: "2026-11-09", week_end: "2026-11-15" }), "09.11–15.11");
  assert.equal(share(80), 0.8);
  assert.equal(share(120), 1);
  assert.equal(share(-5), 0);
});

test("period labels", () => {
  assert.equal(periodLabel("week", "2026-11-09", "2026-11-15"), "9–15 ноября");
  assert.equal(periodLabel("week", "2026-11-30", "2026-12-06"), "30 ноября – 6 декабря");
  assert.equal(periodLabel("month", "2026-11-01", "2026-11-30"), "Ноябрь 2026");
  assert.equal(periodLabel("course", null, "2026-11-14"), "Весь курс");
});

test("period and step live in the address", () => {
  assert.deepEqual(periodFromQuery(null, null), { period: "course", offset: 0 });
  assert.deepEqual(periodFromQuery("month", "-2"), { period: "month", offset: -2 });
  assert.deepEqual(periodFromQuery("week", "x"), { period: "week", offset: 0 });
  assert.deepEqual(periodFromQuery("year", "3"), { period: "course", offset: 0 });
  assert.deepEqual(periodFromQuery("course", "3"), { period: "course", offset: 0 });
  assert.equal(analyticsQuery("course", 0), "tab=analytics");
  assert.equal(analyticsQuery("month", 0), "tab=analytics&period=month");
  assert.equal(analyticsQuery("week", -1), "tab=analytics&period=week&offset=-1");
});
