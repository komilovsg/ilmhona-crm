import assert from "node:assert/strict";
import { test } from "node:test";

import {
  NOT_PAYING,
  fundingLabel,
  fundingProblem,
  payerBody,
  payerKey,
  payerOptions,
  priced,
  studentFunding,
  withDonors,
} from "./funding.ts";

test("donors go with «донор» and «смешанный» only", () => {
  assert.equal(withDonors("донор"), true);
  assert.equal(withDonors("смешанный"), true);
  assert.equal(withDonors("платный"), false);
  assert.equal(withDonors("бесплатный"), false);
  assert.equal(fundingProblem("донор", []), "Выберите хотя бы одного донора");
  assert.equal(fundingProblem("донор", ["a"]), null);
  assert.equal(fundingProblem("смешанный", []), null);
  assert.equal(fundingProblem("платный", []), null);
});

test("labels of a cohort and of a student", () => {
  assert.equal(fundingLabel("донор"), "За счёт донора");
  const donors = [{ id: "a", name: "Фонд" }];

  assert.equal(studentFunding("смешанный", "a", donors), "Донор: Фонд");
  assert.equal(studentFunding("смешанный", null, donors), "Платит сам");
  assert.equal(studentFunding("бесплатный", null, donors), "Бесплатно");
});

test("«Не платит» is offered in paid and mixed cohorts only, never with a donor", () => {
  assert.equal(priced("платный"), true);
  assert.equal(priced("смешанный"), true);
  assert.equal(priced("бесплатный"), false);
  assert.equal(priced("донор"), false);
  const donors = [{ id: "a", name: "Фонд" }];

  assert.deepEqual(payerOptions("платный", donors), [{ key: NOT_PAYING, label: "Не платит" }]);
  assert.deepEqual(payerOptions("смешанный", donors), [
    { key: NOT_PAYING, label: "Не платит" },
    { key: "a", label: "Донор: Фонд" },
  ]);
  assert.deepEqual(payerOptions("донор", donors), [{ key: "a", label: "Фонд" }]);
  assert.deepEqual(payerOptions("бесплатный", donors), []);
  assert.deepEqual(payerBody(NOT_PAYING), { donor_id: null, not_paying: true });
  assert.deepEqual(payerBody("a"), { donor_id: "a", not_paying: false });
  assert.deepEqual(payerBody(null), { donor_id: null, not_paying: false });
  assert.equal(payerKey(null, true), NOT_PAYING);
  assert.equal(payerKey("a", false), "a");
  assert.equal(studentFunding("платный", null, donors, true), "Не платит");
});
