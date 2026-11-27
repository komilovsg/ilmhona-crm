import assert from "node:assert/strict";
import { test } from "node:test";

import { fundingLabel, fundingProblem, studentFunding, withDonors } from "./funding.ts";

test("donors go with «донор» and «смешанный» only", () => {
  assert.equal(withDonors("донор"), true);
  assert.equal(withDonors("смешанный"), true);
  assert.equal(withDonors("платный"), false);
  assert.equal(withDonors("бесплатный"), false);
  assert.equal(fundingProblem("донор", []), "Выберите хотя бы одного донора");
  assert.equal(fundingProblem("донор", ["a"]), null);
  assert.equal(fundingProblem("платный", []), null);
});

test("labels of a cohort and of a student", () => {
  assert.equal(fundingLabel("донор"), "За счёт донора");
  const donors = [{ id: "a", name: "Фонд" }];

  assert.equal(studentFunding("смешанный", "a", donors), "Донор: Фонд");
  assert.equal(studentFunding("смешанный", null, donors), "Платит сам");
  assert.equal(studentFunding("бесплатный", null, donors), "Бесплатно");
});
