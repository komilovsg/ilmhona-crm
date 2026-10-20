import assert from "node:assert/strict";
import { test } from "node:test";

import { changedKeys, conflictLines, rebase, staleOf, whoWhen } from "./conflict.ts";

const old = { name: "Алиев", phone: "+992900000001", days: [1, 3] };

test("only the fields the user changed are sent", () => {
  assert.deepEqual(changedKeys(old, { ...old, phone: "+992930000002" }), ["phone"]);
  assert.deepEqual(changedKeys(old, { ...old, days: [1, 3] }), []);
  assert.deepEqual(changedKeys(old, { ...old, days: [1, 4] }), ["days"]);
});

test("rebase keeps my change and takes everything else from the fresh record", () => {
  const fresh = { name: "Алиев А.", phone: "+992930000002", days: [1, 3] };
  const mine = { ...old, phone: "+992999999999" };

  assert.deepEqual(rebase(old, fresh, mine), { name: "Алиев А.", phone: "+992999999999", days: [1, 3] });
});

test("two people editing different fields both survive a rebase", () => {
  const fresh = { ...old, phone: "+992930000002" }; // theirs
  const mine = { ...old, name: "Алишер" };

  assert.deepEqual(rebase(old, fresh, mine), { name: "Алишер", phone: "+992930000002", days: [1, 3] });
});

test("a 409 stale_version problem is recognised, any other error is not", () => {
  const problem = {
    status: 409,
    code: "stale_version",
    params: { version: 3, changed_by: "Курбон", changed_at: "2026-10-20T09:05:00+00:00", current: { id: "s1" } },
  };

  assert.deepEqual(staleOf(problem), {
    current: { id: "s1" },
    version: 3,
    changedBy: "Курбон",
    changedAt: "2026-10-20T09:05:00+00:00",
  });
  assert.equal(staleOf({ status: 409, code: "already_enrolled" }), null);
  assert.equal(staleOf(new Error("x")), null);
});

test("the dialog lines show my value and the one in the database", () => {
  const lines = conflictLines(["phone", "days"], { ...old, phone: "+992999" }, { ...old, phone: "+992930" }, {
    phone: "Телефон",
  });

  assert.deepEqual(lines, [
    { label: "Телефон", mine: "+992999", theirs: "+992930" },
    { label: "days", mine: "1, 3", theirs: "1, 3" },
  ]);
});

test("who and when, in Dushanbe time (UTC+5)", () => {
  assert.equal(whoWhen({ changedBy: "Курбон", changedAt: "2026-10-20T09:05:00+00:00" }), "Запись изменил Курбон в 14:05.");
  assert.equal(whoWhen({ changedBy: null, changedAt: null }), "Запись изменил другой пользователь.");
});
