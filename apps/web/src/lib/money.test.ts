import assert from "node:assert/strict";
import { test } from "node:test";

import {
  amountText,
  methodLabel,
  monthLabel,
  monthOptions,
  paidMonthsLabel,
  paymentTone,
  salaryTone,
  shiftMonth,
  validAmount,
  validRate,
} from "./money.ts";

test("month labels and shifting cross the year", () => {
  assert.equal(monthLabel("2026-10-01"), "октябрь 2026");
  assert.equal(monthLabel("2027-01"), "январь 2027");
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2026-01", -1), "2025-12");
});

test("month options: newest first, the current month inside", () => {
  const options = monthOptions("2026-10", 2, 1);

  assert.deepEqual(
    options.map((o) => o.key),
    ["2026-11", "2026-10", "2026-09", "2026-08"],
  );
  assert.equal(options[1].label, "октябрь 2026");
});

test("paid months read as «1, 2 из 4»", () => {
  assert.equal(paidMonthsLabel([1, 2], 4), "1, 2 из 4");
  assert.equal(paidMonthsLabel([], 3), "0 из 3");
});

test("amounts: 500.00 and 500 are the same, bad input is not an amount", () => {
  assert.equal(amountText("500.00"), "500");
  assert.equal(amountText(450.5), "450.5");
  assert.equal(amountText("1 000"), "");
  assert.equal(validAmount("450,50"), true);
  assert.equal(validAmount("0"), false);
  assert.equal(validAmount("-1"), false);
  assert.equal(validAmount("10.999"), false);
  assert.equal(validAmount("0.07"), true); // 0.07 * 100 is not an integer in floating point
  assert.equal(validAmount(""), false);
});

test("a rate may be zero but not negative", () => {
  assert.equal(validRate("0"), true);
  assert.equal(validRate("1500.5"), true);
  assert.equal(validRate("-1"), false);
  assert.equal(validRate(""), false);
});

test("tones and method labels", () => {
  assert.equal(paymentTone("подтверждено"), "success");
  assert.equal(paymentTone("ожидает"), "warning");
  assert.equal(salaryTone("выплачено"), "success");
  assert.equal(salaryTone("к выплате"), "danger");
  assert.equal(methodLabel("alif"), "Alif");
  assert.equal(methodLabel("наличные"), "Наличные");
});
