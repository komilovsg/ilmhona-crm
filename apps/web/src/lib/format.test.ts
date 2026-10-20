import assert from "node:assert/strict";
import { test } from "node:test";

import { dushanbeDay, telHref } from "./format.ts";

test("tel: hrefs have no spaces or punctuation", () => {
  assert.equal(telHref("+992 900 12-34-56"), "tel:+992900123456");
  assert.equal(telHref("900 12 34 56"), "tel:+992900123456");
  assert.equal(telHref("992900123456"), "tel:+992900123456");
  assert.equal(telHref("+992 (900) 123456"), "tel:+992900123456");
});

test("a timestamp is shown on its Asia/Dushanbe day, not the UTC day", () => {
  assert.equal(dushanbeDay("2026-10-20T20:30:00Z"), "2026-10-21"); // 01:30 next day in UTC+5
  assert.equal(dushanbeDay("2026-10-21T10:00:00Z"), "2026-10-21");
});
