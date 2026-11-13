import assert from "node:assert/strict";
import { test } from "node:test";

import { charsLeft, isSaveShortcut, metricOf, progressText, statusTone, validTarget } from "./goals.ts";

test("status tones carry meaning for every status", () => {
  assert.equal(statusTone("достигнута"), "success");
  assert.equal(statusTone("по графику"), "primary");
  assert.equal(statusTone("отстаём"), "warning");
  assert.equal(statusTone("срок прошёл"), "danger");
});

test("progress text uses the unit of the metric", () => {
  assert.equal(progressText(412, 1000, "graduates_total"), "412 из 1 000");
  assert.equal(progressText(850, 1000, "income"), "850 из 1 000 TJS");
  assert.equal(progressText(72.5, 90, "collection_rate_month"), "72,5 из 90 %");
});

test("unknown metric falls back to the first one", () => {
  assert.equal(metricOf("nope").key, "graduates_total");
});

test("target must be positive, a percentage at most 100", () => {
  assert.equal(validTarget("1 000", "income"), true);
  assert.equal(validTarget("0", "income"), false);
  assert.equal(validTarget("abc", "income"), false);
  assert.equal(validTarget("90,5", "collection_rate_month"), true);
  assert.equal(validTarget("101", "collection_rate_month"), false);
});

test("counter and save shortcut", () => {
  assert.equal(charsLeft("abc", 280), 277);
  assert.equal(charsLeft("x".repeat(300), 280), 0);
  assert.equal(isSaveShortcut({ key: "Enter", ctrlKey: true, metaKey: false }), true);
  assert.equal(isSaveShortcut({ key: "Enter", ctrlKey: false, metaKey: true }), true);
  assert.equal(isSaveShortcut({ key: "Enter", ctrlKey: false, metaKey: false }), false);
});
