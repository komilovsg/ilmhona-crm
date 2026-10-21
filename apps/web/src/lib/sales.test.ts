import assert from "node:assert/strict";
import { test } from "node:test";

import { fromLocalInput, localInput, messengerDigits, moneyOrDash, telegramHref, whatsappHref } from "./sales.ts";

test("messenger links carry digits only, with 992 for a local number", () => {
  assert.equal(messengerDigits("+992 90 111-22-33"), "992901112233");
  assert.equal(whatsappHref("901112233"), "https://wa.me/992901112233");
  assert.equal(telegramHref("+992 90 111 22 33"), "https://t.me/+992901112233");
  assert.equal(whatsappHref("12"), null);
  assert.equal(whatsappHref(null), null);
});

test("CPL and CAC read «—» when there is no number", () => {
  assert.equal(moneyOrDash(null), "—");
  assert.match(moneyOrDash("250.00"), /^250 TJS$/);
});

test("datetime-local values round-trip in Dushanbe time", () => {
  assert.equal(fromLocalInput("2026-10-21T09:30"), "2026-10-21T09:30:00+05:00");
  assert.equal(localInput("2026-10-21T04:30:00Z"), "2026-10-21T09:30");
  assert.equal(fromLocalInput(""), null);
});
