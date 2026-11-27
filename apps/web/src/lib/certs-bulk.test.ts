import assert from "node:assert/strict";
import { test } from "node:test";

import { bulkFileReason, fileProblem, issueLabel } from "./certs-bulk.ts";

test("only a small .xlsx is sent", () => {
  assert.equal(fileProblem({ name: "Список.XLSX", size: 1000 }), null);
  assert.match(fileProblem({ name: "list.csv", size: 10 }) ?? "", /xlsx/);
  assert.match(fileProblem({ name: "list.xlsx", size: 3 * 1024 * 1024 }) ?? "", /2 МБ/);
});

test("a file error is explained in Russian, other errors are not", () => {
  assert.match(bulkFileReason({ status: 422, code: "cert_bulk_file", params: { reason: "too_many_rows" } }) ?? "", /500/);
  assert.match(bulkFileReason({ status: 422, code: "cert_bulk_file", params: { reason: "other" } }) ?? "", /xlsx/);
  assert.equal(bulkFileReason({ status: 500, code: "internal_error" }), null);
  assert.equal(bulkFileReason(null), null);
});

test("the issue button agrees the word with the number", () => {
  assert.equal(issueLabel(1), "Выдать 1 сертификат");
  assert.equal(issueLabel(3), "Выдать 3 сертификата");
  assert.equal(issueLabel(11), "Выдать 11 сертификатов");
  assert.equal(issueLabel(21), "Выдать 21 сертификат");
});
