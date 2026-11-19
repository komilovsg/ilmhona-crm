import assert from "node:assert/strict";
import { test } from "node:test";

import { PDFDocument } from "pdf-lib";
import { unzipSync } from "fflate";

import {
  canIssueCohort,
  canIssueToNonGraduate,
  fetchAll,
  issueLabel,
  mergePdfs,
  progressLabel,
  selectable,
  uniqueName,
  zipPdfs,
  type CheckItem,
} from "./certs.ts";

async function pdf(pages: number): Promise<Uint8Array> {
  const doc = await PDFDocument.create();

  for (let i = 0; i < pages; i++) doc.addPage([200, 100]);

  return doc.save();
}

const item = (status: CheckItem["status"]): CheckItem => ({
  enrollment_id: status,
  student_name: status,
  enrollment_status: "выпускник",
  number: null,
  certificate_id: null,
  reason: null,
  text: null,
  score: 80,
  status,
});

test("progress reads «12 из 18»", () => {
  assert.equal(progressLabel(12, 18), "12 из 18");
  assert.equal(issueLabel(3), "Выдать 3");
  assert.equal(issueLabel(0), "Выдать");
});

test("only ready rows are selectable", () => {
  assert.deepEqual(selectable([item("ready"), item("issued"), item("fix")]).map((i) => i.status), ["ready"]);
});

test("file names stay unique inside one archive", () => {
  const used = new Set<string>();

  assert.equal(uniqueName("a.pdf", used), "a.pdf");
  assert.equal(uniqueName("a.pdf", used), "a (2).pdf");
  assert.equal(uniqueName("a.pdf", used), "a (3).pdf");
});

test("fetchAll goes one by one in order and reports progress", async () => {
  const log: string[] = [];
  let running = 0;
  let peak = 0;
  const files = await fetchAll(
    ["x", "y", "z"],
    async (id) => {
      peak = Math.max(peak, ++running);
      await new Promise((r) => setTimeout(r, 2));
      running--;
      log.push(`get ${id}`);

      return { data: new Uint8Array([1]), name: id === "y" ? null : "same.pdf" };
    },
    (done, total) => log.push(progressLabel(done, total)),
  );

  assert.equal(peak, 1);
  assert.deepEqual(files.map((f) => f.name), ["same.pdf", "y.pdf", "same (2).pdf"]);
  assert.deepEqual(log.filter((l) => l.includes("из")), ["0 из 3", "1 из 3", "2 из 3", "3 из 3"]);
});

test("a failed download stops the run", async () => {
  await assert.rejects(
    fetchAll(
      ["a", "b"],
      async (id) => {
        if (id === "b") throw new Error("boom");

        return { data: new Uint8Array(), name: null };
      },
      () => undefined,
    ),
    /boom/,
  );
});

test("merge keeps every page in order", async () => {
  const merged = await mergePdfs([
    { name: "a.pdf", data: await pdf(1) },
    { name: "b.pdf", data: await pdf(2) },
  ]);

  assert.equal((await PDFDocument.load(merged)).getPageCount(), 3);
});

test("zip holds each file under its name", async () => {
  const a = await pdf(1);
  const out = unzipSync(zipPdfs([{ name: "n1_ali.pdf", data: a }, { name: "n2_vali.pdf", data: a }]));

  assert.deepEqual(Object.keys(out).sort(), ["n1_ali.pdf", "n2_vali.pdf"]);
  assert.equal(out["n1_ali.pdf"].length, a.length);
});

test("permission gating of the issue buttons", () => {
  assert.equal(canIssueCohort({ certificates: "change" }, 2), true);
  assert.equal(canIssueCohort({ certificates: "change" }, 0), false);
  assert.equal(canIssueCohort({ certificates: "view" }, 2), false);
  assert.equal(canIssueToNonGraduate({ cert_templates: "change" }, true), true);
  assert.equal(canIssueToNonGraduate({ cert_templates: "change" }, false), false);
  assert.equal(canIssueToNonGraduate({ cert_templates: "view" }, true), false);
});
