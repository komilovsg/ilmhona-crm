import assert from "node:assert/strict";
import { test } from "node:test";

import { dayMonth, laneSpan, layoutBody, moveCard, plural, signed, todayAt, trendOf, weekdayDate, whatsappHref } from "./dash.ts";

test("plural forms", () => {
  const f = (n: number) => plural(n, "лид", "лида", "лидов");

  assert.deepEqual([1, 2, 5, 11, 12, 21, 24, 25, 111].map(f), ["лид", "лида", "лидов", "лидов", "лидов", "лид", "лида", "лидов", "лидов"]);
});

test("trend is always text, none against zero", () => {
  assert.deepEqual(trendOf(48.4), { text: "▲ 48 %", tone: "up" });
  assert.deepEqual(trendOf(-8), { text: "▼ 8 %", tone: "down" });
  assert.deepEqual(trendOf(0), { text: "0 %", tone: "flat" });
  assert.deepEqual(trendOf(null), { text: "новое", tone: "new" });
  assert.equal(signed(9), "+9");
  assert.equal(signed(-3), "−3");
  assert.equal(signed(0), "0");
});

test("lane span is a share of the window, clipped to it", () => {
  const w: [string, string] = ["2026-11-01", "2027-01-31"]; // 92 days
  const full = laneSpan("2026-11-01", "2027-01-31", ...w);

  assert.equal(full.left, 0);
  assert.equal(Math.round(full.width), 100);
  const clipped = laneSpan("2026-09-01", "2026-12-01", ...w);

  assert.equal(clipped.left, 0);
  assert.equal(Math.round(clipped.width), 34); // Nov 1 .. Dec 1 = 31 of 92 days
  const late = laneSpan("2027-01-20", "2027-06-01", ...w);

  assert.ok(late.left > 80 && late.left + late.width <= 100.0001);
  assert.ok(laneSpan("2026-11-10", "2026-11-10", ...w).width >= 1.5); // a one-day cohort stays visible
});

test("today line inside the window, clamped outside", () => {
  assert.equal(Math.round(todayAt("2026-11-14", "2026-11-01", "2027-01-31")), 14);
  assert.equal(todayAt("2026-10-01", "2026-11-01", "2027-01-31"), 0);
  assert.equal(todayAt("2028-01-01", "2026-11-01", "2027-01-31"), 100);
});

test("dates in Russian", () => {
  assert.equal(dayMonth("2026-11-14"), "14 ноября");
  assert.equal(weekdayDate("2026-11-14"), "суббота, 14 ноября");
});

test("moving a card by one place stops at the ends", () => {
  const cards = [{ id: "a" }, { id: "b" }, { id: "c" }];

  assert.deepEqual(moveCard(cards, { id: "b", delta: -1 }).map((c) => c.id), ["b", "a", "c"]);
  assert.deepEqual(moveCard(cards, { id: "c", delta: 1 }), cards);
  assert.deepEqual(moveCard(cards, { id: "a", delta: -1 }), cards);
  assert.deepEqual(moveCard(cards, { id: "zz", delta: 1 }), cards);
});

test("layout body lists every card and the hidden ones", () => {
  assert.deepEqual(
    layoutBody([
      { id: "a", title: "A", visible: true },
      { id: "b", title: "B", visible: false },
    ]),
    { order: ["a", "b"], hidden: ["b"] },
  );
});

test("whatsapp link keeps digits only", () => {
  assert.equal(whatsappHref("+992 90-000-00-01"), "https://wa.me/992900000001");
});
