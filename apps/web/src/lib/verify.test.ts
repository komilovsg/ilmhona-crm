import assert from "node:assert/strict";
import { test } from "node:test";

import { formatDay, normalizeCode, showCode, studyPeriod, type PublicCertificate } from "./verify.ts";

test("a typed code is normalised; anything else is not a code", () => {
  assert.equal(normalizeCode("abcd-efgh-jk23"), "ABCDEFGHJK23");
  assert.equal(normalizeCode(" ABCD EFGH JK23 "), "ABCDEFGHJK23");
  assert.equal(normalizeCode("CERT-2026-0001"), null);
  assert.equal(normalizeCode("ABCDEFGHJK2"), null);
  assert.equal(normalizeCode("ABCDEFGHJK0O"), null);
  assert.equal(normalizeCode("../../api/v1/me"), null);
});

test("the code shows in groups of four", () => {
  assert.equal(showCode("ABCDEFGHJK23"), "ABCD-EFGH-JK23");
});

test("dates read in Russian", () => {
  assert.equal(formatDay("2026-11-27"), "27 ноября 2026");
  const base = { cohort_start: "2026-03-02", cohort_end: "2026-11-18" } as PublicCertificate;
  assert.equal(studyPeriod(base), "2 марта 2026 — 18 ноября 2026");
  assert.equal(studyPeriod({ ...base, cohort_start: null, cohort_end: null }), null);
});
