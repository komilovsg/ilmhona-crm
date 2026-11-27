import assert from "node:assert/strict";
import { test } from "node:test";

import {
  debtLines,
  defaultMonth,
  discountLine,
  discountOf,
  discountText,
  dueText,
  holdText,
  monthConflictText,
  monthKind,
  monthOptionLabel,
  monthStateLabel,
  nextOpenMonth,
  paidCountLabel,
  paidText,
  partialAmountOk,
  percentOf,
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
  assert.equal(monthOptionLabel(2, states[1]), "2-й · 200 / 500");
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

test("debtLines: equal amounts grouped, different listed, awaiting apart", () => {
  assert.deepEqual(debtLines([{ month_no: 1, remaining: "600.00" }, { month_no: 3, remaining: "600.00" }]), [
    "Не оплачены 1-й и 3-й мес. · по 600 TJS",
  ]);
  assert.deepEqual(debtLines([{ month_no: 3, remaining: "600.00" }]), ["Не оплачен 3-й мес. · 600 TJS"]);
  assert.deepEqual(debtLines([{ month_no: 1, remaining: "600.00" }, { month_no: 3, remaining: "400.00" }]), [
    "Не оплачены: 1-й — 600, 3-й — 400 TJS",
  ]);
  assert.deepEqual(debtLines([{ month_no: 1, remaining: "500.00" }, { month_no: 2, remaining: "500.00", awaiting: true }]), [
    "Не оплачен 1-й мес. · 500 TJS",
    "Ожидает подтверждения: 2-й мес. · 500 TJS",
  ]);
});

test("monthKind: four distinct kinds", () => {
  assert.equal(monthKind({ state: "оплачен" }), "paid");
  assert.equal(monthKind({ state: "оплачен", awaiting: true }), "awaiting");
  assert.equal(monthKind({ state: "не оплачен", started: true }), "unpaid");
  assert.equal(monthKind({ state: "частично" }), "unpaid");
  assert.equal(monthKind({ state: "не оплачен", started: false }), "future");
});

test("a discount is a percent of the month's price, cents rounded half up like the server", () => {
  assert.equal(discountOf("500.00", 20), 100);
  assert.equal(discountOf(500, 100), 500);
  assert.equal(discountOf("333.33", 15), 50); // 49.9995 -> 50.00
  assert.equal(discountOf("0.10", 5), 0.01); // 0.005 -> 0.01
  assert.equal(discountOf(500, 0), 0);
  assert.equal(discountOf(500, 101), 0);
  assert.equal(discountOf(500, 2.5), 0);
});

test("the typed percent is a whole number 1–100", () => {
  assert.equal(percentOf("20"), 20);
  assert.equal(percentOf(" 100 "), 100);
  for (const bad of ["", "0", "101", "2.5", "-5", "abc", "1000"]) assert.equal(percentOf(bad), null, bad);
});

test("the live line shows the price, the discount and what is left to pay", () => {
  assert.equal(discountLine("500.00", "500.00", 20), "Цена месяца 500 TJS − 100 TJS (20%) = к оплате 400 TJS");
  assert.equal(discountLine("500.00", "500.00", 100), "Цена месяца 500 TJS − 500 TJS (100%) = к оплате 0 TJS");
  assert.equal(discountLine("500.00", "300.00", 20), "Остаток месяца 300 TJS − 100 TJS (20%) = к оплате 200 TJS");
});

test("a month with a discount is measured against the discounted price", () => {
  assert.equal(monthStateLabel({ state: "частично", paid: "200.00", price: "500.00", discount: "100.00" }), "частично: 200 из 400 TJS");
  assert.equal(
    monthOptionLabel(1, { state: "частично", paid: "200.00", price: "500.00", pending: "300.00", discount: "100.00" }),
    "1-й · 200 / 400 · ожидает",
  );
  assert.equal(discountText({ discount_percent: 20, discount_amount: "100.00" }), "20% · 100 TJS");
  assert.equal(discountText({ discount_percent: null, discount_amount: "0.00" }), null);
});
