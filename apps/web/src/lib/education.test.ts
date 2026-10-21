import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addDays,
  formatPrice,
  cohortTone,
  dayTitle,
  daysLabel,
  fillPercent,
  isoWeekday,
  mondayOf,
  scheduleProblem,
  timeProblem,
  todayIso,
  weekOf,
} from "./education.ts";

test("daysLabel sorts ISO weekdays", () => {
  assert.equal(daysLabel([5, 1, 3]), "Пн, Ср, Пт");
  assert.equal(daysLabel([7]), "Вс");
});

test("fillPercent is clamped to 0..100", () => {
  assert.equal(fillPercent(5, 20), 25);
  assert.equal(fillPercent(4, 3), 100);
  assert.equal(fillPercent(0, 0), 0);
});

test("week math works on ISO dates across month and year ends", () => {
  assert.equal(isoWeekday("2030-03-03"), 7);
  assert.equal(isoWeekday("2030-03-04"), 1);
  assert.equal(mondayOf("2030-03-10"), "2030-03-04");
  assert.equal(addDays("2029-12-31", 1), "2030-01-01");
  assert.deepEqual(
    weekOf("2030-03-06").map((d) => d.slice(8)),
    ["04", "05", "06", "07", "08", "09", "10"],
  );
  assert.equal(dayTitle("2030-03-04"), "Пн 04.03");
});

test("todayIso uses Asia/Dushanbe (UTC+5)", () => {
  assert.equal(todayIso(new Date("2030-03-04T20:00:00Z")), "2030-03-05");
  assert.equal(todayIso(new Date("2030-03-04T18:59:00Z")), "2030-03-04");
});

test("cohort status tones", () => {
  assert.equal(cohortTone("активный"), "success");
  assert.equal(cohortTone("завершён"), "default");
});

test("scheduleProblem mirrors the API rules (#6 #8)", () => {
  const ok = { start: "2030-03-04", end: "2030-04-04", startTime: "10:00", endTime: "11:30", weekdays: [1] };

  assert.equal(scheduleProblem(ok), null);
  assert.match(scheduleProblem({ ...ok, start: "2001-07-01", end: "2001-08-01" }) ?? "", /2020/);
  assert.match(scheduleProblem({ ...ok, end: "2030-03-04" }) ?? "", /позже/);
  assert.match(scheduleProblem({ ...ok, startTime: "04:35", endTime: "05:35" }) ?? "", /07:00/);
  assert.match(scheduleProblem({ ...ok, weekdays: [] }) ?? "", /день/);
  assert.match(timeProblem("10:00", "10:20") ?? "", /30 минут/);
  assert.match(timeProblem("10:00", "14:30") ?? "", /4 часов/);
  assert.equal(timeProblem("07:00", "08:00"), null);
  assert.equal(timeProblem("20:30", "22:00"), null);
});

test("prices show kopecks only when there are some", () => {
  assert.equal(formatPrice("650.00").replace(/\s/g, " "), "650 TJS");
  assert.equal(formatPrice("3450.5").replace(/\s/g, " "), "3 450,50 TJS");
  assert.equal(formatPrice(1200).replace(/\s/g, " "), "1 200 TJS");
});
