import assert from "node:assert/strict";
import { test } from "node:test";

import { directorFor, withDirector } from "./director.ts";

const byLang = {
  ru: { name: "Озодамо", title: "Директор" },
  en: { name: "Ozodamo", title: "CEO" },
  tg: { name: "", title: "" },
};

test("the director follows the language, empty parts fall back to Russian", () => {
  assert.deepEqual(directorFor(byLang, "en"), { name: "Ozodamo", title: "CEO" });
  assert.deepEqual(directorFor(byLang, "tg"), { name: "Озодамо", title: "Директор" });
  assert.deepEqual(directorFor({ ...byLang, en: { name: "", title: "CEO" } }, "en"), { name: "Озодамо", title: "CEO" });
  assert.deepEqual(directorFor(byLang, "xx"), { name: "Озодамо", title: "Директор" });
  assert.equal(directorFor(undefined, "en"), null);
});

test("sample values get the director of the language", () => {
  const sample = { "student.full_name": "А", "company.director_name": "Образцов" };

  assert.equal(withDirector(sample, byLang, "en")?.["company.director_name"], "Ozodamo");
  assert.equal(withDirector(sample, byLang, "en")?.["student.full_name"], "А");
  assert.equal(withDirector(sample, undefined, "en"), sample);
});
