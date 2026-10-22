import assert from "node:assert/strict";
import { test } from "node:test";

import { errorText } from "./api-errors.ts";

test("busy messages show the day as dd.mm.yyyy", () => {
  const params = { cohort: "G-1", date: "2026-11-17", start: "10:00", end: "11:30" };

  assert.equal(errorText("room_busy", params), "Аудитория занята потоком G-1: 17.11.2026, 10:00–11:30.");
  assert.equal(
    errorText("instructor_busy", params),
    "Инструктор в это время ведёт урок: поток G-1, 17.11.2026, 10:00–11:30.",
  );
});
