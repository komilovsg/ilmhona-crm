import assert from "node:assert/strict";
import { test } from "node:test";

import {
  defaultMonth,
  dueText,
  holdText,
  monthConflictText,
  monthOptionLabel,
  monthStateLabel,
  nextOpenMonth,
  paidCountLabel,
  paidText,
  partialAmountOk,
  whenText,
} from "./payment-month.ts";

const pending = {
  id: "p1",
  amount: "700.00",
  method: "наличные",
  paid_at: "2026-10-21",
  status: "ожидает",
  created_by: "Курбонзода Курбонмухаммад",
  created_at: "2026-10-21T08:39:00Z", // 13:39 in Dushanbe
};

test("the default month is the first one that is not full", () => {
  assert.equal(defaultMonth(4, []), 1);
  assert.equal(defaultMonth(4, [1]), 2);
  assert.equal(defaultMonth(4, [1, 2, 4]), 3);
  assert.equal(defaultMonth(3, [1, 2, 3]), null);
  assert.equal(defaultMonth(0, []), null);
});

test("after a month fills up the next open one is suggested", () => {
  assert.equal(nextOpenMonth(4, [1], 2), 3);
  assert.equal(nextOpenMonth(4, [3], 2), 4);
  assert.equal(nextOpenMonth(4, [3, 4], 2), 1);
  assert.equal(nextOpenMonth(2, [1], 2), null);
});

test("who paid the month reads like the owner asked", () => {
  assert.equal(whenText(pending.created_at), "21.10 в 13:39");
  assert.equal(
    paidText({ month_no: 2, paid: "700.00", payments: [pending] }),
    "Месяц 2 уже оплачен: 700 TJS — Курбонзода Курбонмухаммад, 21.10 в 13:39 (ожидает подтверждения)",
  );
  const two = paidText({
    month_no: 2,
    paid: "700.00",
    payments: [
      { ...pending, amount: "300.00", status: "подтверждено", created_by: null },
      { ...pending, amount: "400.00" },
    ],
  });
  assert.match(two, /^Месяц 2 уже оплачен: 700 TJS \(300 TJS — импорт, .*\(подтверждено\); 400 TJS — Курбонзода/);
  assert.equal(holdText("Анна", 2), "Анна сейчас вносит оплату за месяц 2");
});

test("a 409 of the month rule becomes the same message, other errors do not", () => {
  const params = { month_no: 2, paid: "700.00", remaining: "0.00", payments: [pending] };
  assert.equal(monthConflictText({ code: "month_already_paid", params }), paidText(params));
  assert.match(
    monthConflictText({ code: "month_overpaid", params: { ...params, paid: "500.00", remaining: "200.00" } }) ?? "",
    /^За месяц 2 осталось оплатить 200 TJS\. Уже внесено: 500 TJS — Курбонзода/,
  );
  assert.equal(monthConflictText({ code: "stale_version", params: {} }), null);
  assert.equal(monthConflictText(null), null);
});

test("month states and the partial amount", () => {
  assert.equal(monthStateLabel({ state: "не оплачен", paid: "0.00", price: "500.00" }), "не оплачен");
  assert.equal(monthStateLabel({ state: "частично", paid: "200.00", price: "500.00" }), "частично: 200 из 500 TJS");
  assert.equal(monthStateLabel({ state: "оплачен", paid: "500.00", price: "500.00" }), "оплачен");
  // old-system overpayment: shown as such, never a negative remaining
  assert.equal(monthStateLabel({ state: "оплачен", paid: "700.00", price: "500.00", overpaid: "200.00" }), "переплата 200 TJS");
  assert.match(
    paidText({ month_no: 2, paid: "700.00", overpaid: "200.00", payments: [pending] }),
    /^Месяц 2 уже оплачен \(переплата 200 TJS\): 700 TJS — /,
  );
  // one definition with the cap: a month covered by a pending payment is «оплачен» everywhere
  const states = [
    { month_no: 1, state: "оплачен" as const, paid: "500.00", pending: "500.00", price: "500.00" },
    { month_no: 2, state: "частично" as const, paid: "200.00", pending: "0.00", price: "500.00" },
    { month_no: 3, state: "оплачен" as const, paid: "500.00", pending: "0.00", price: "500.00" },
  ];
  assert.equal(paidCountLabel(states, 4), "2 из 4 (1 ожидает подтверждения)");
  assert.equal(paidCountLabel([states[2]], 4), "1 из 4");
  assert.equal(monthOptionLabel(1, states[0]), "1-й · оплачен · ожидает");
  assert.equal(monthOptionLabel(2, states[1]), "2-й · частично: 200 из 500 TJS");
  assert.equal(monthOptionLabel(4, undefined), "4-й");
  assert.ok(partialAmountOk("200", "200.00"));
  assert.ok(partialAmountOk("0.5", "200"));
  for (const bad of ["0", "", "200.01", "-1", "abc"]) assert.ok(!partialAmountOk(bad, "200.00"), bad);
  assert.equal(
    dueText([
      { month_no: 2, remaining: "300.00" },
      { month_no: 3, remaining: "500.00" },
    ]),
    "2: 300 TJS, 3: 500 TJS",
  );
});
