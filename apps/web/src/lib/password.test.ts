import assert from "node:assert/strict";
import { test } from "node:test";

import { canSubmit, checkRules, strengthOf, type PasswordPolicy } from "./password.ts";

const policy: PasswordPolicy = {
  min_length: 10,
  max_length: 72,
  rules: [
    { id: "length", label: "10–72" },
    { id: "letter", label: "буква" },
    { id: "digit", label: "цифра" },
    { id: "not_login", label: "не логин" },
    { id: "not_current", label: "не текущий" },
  ],
};
const ok = (pw: string, login = "anna", current = "Old-pass-1") =>
  Object.fromEntries(checkRules(pw, policy, login, current).map((r) => [r.id, r.ok]));

test("empty password passes nothing", () => {
  assert.ok(Object.values(ok("")).every((v) => !v));
});

test("each rule turns green on its own", () => {
  assert.deepEqual(ok("Ab1"), { length: false, letter: true, digit: true, not_login: true, not_current: true });
  assert.equal(ok("1234567890").letter, false);
  assert.equal(ok("abcdefghij").digit, false);
  assert.equal(ok("абвгдеж1").letter, true);
  assert.equal(ok("ANNA", "anna").not_login, false);
  assert.equal(ok("Old-pass-1").not_current, false);
  assert.equal(ok("A".repeat(73)).length, false);
});

test("submit needs every rule and a matching confirm", () => {
  const rules = checkRules("Brand-new-1", policy, "anna", "Old-pass-1");
  assert.equal(canSubmit(rules, "Brand-new-1", "Brand-new-1"), true);
  assert.equal(canSubmit(rules, "Brand-new-1", "Brand-new-"), false);
  assert.equal(canSubmit(checkRules("weak", policy, "anna", ""), "weak", "weak"), false);
});

test("strength grows with length and classes", () => {
  assert.equal(strengthOf("").level, 0);
  assert.equal(strengthOf("abcdefgh").label, "слабый");
  assert.equal(strengthOf("Abcdefghi1").label, "средний");
  assert.equal(strengthOf("Abcdefghij1!").label, "надёжный");
});
