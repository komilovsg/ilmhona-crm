import assert from "node:assert/strict";
import { test } from "node:test";

import { dismissToast, getToasts, MAX_TOASTS, notify, TOAST_MS } from "./toast-store.ts";

test("at most 3 toasts are visible: the oldest leaves when a 4th arrives", () => {
  for (const t of getToasts()) dismissToast(t.id);
  ["a", "b", "c", "d"].forEach(notify);
  assert.equal(getToasts().length, MAX_TOASTS);
  assert.deepEqual(getToasts().map((t) => t.title), ["b", "c", "d"]);
  for (const t of getToasts()) dismissToast(t.id);
  assert.equal(getToasts().length, 0);
});

test("errors stay longer than successes", () => {
  assert.ok(TOAST_MS.success >= 4000 && TOAST_MS.success <= 5000);
  assert.equal(TOAST_MS.error, 7000);
});
