import assert from "node:assert/strict";
import { test } from "node:test";

import { move, newCategoryName, parsePercent, parseScore, removedCategories, schemeProblems, schemeSum, weightsLabel } from "./grading.ts";

const STANDARD = [
  { key: "attendance", name: "Посещаемость", weight: 20, kind: "attendance" as const },
  { key: "homework", name: "Домашние задания", weight: 40, kind: "manual" as const },
  { key: "final", name: "Финал", weight: 40, kind: "manual" as const },
];

test("score input accepts empty and 0..weight whole numbers only", () => {
  assert.deepEqual(parseScore("", 40), { ok: true, value: null });
  assert.deepEqual(parseScore(" 35 ", 40), { ok: true, value: 35 });
  assert.deepEqual(parseScore("0", 40), { ok: true, value: 0 });
  assert.deepEqual(parseScore("40", 40), { ok: true, value: 40 });
  assert.deepEqual(parseScore("20", 20), { ok: true, value: 20 });
  for (const bad of ["41", "-1", "3.5", "abc", "100"]) assert.deepEqual(parseScore(bad, 40), { ok: false });
  assert.deepEqual(parseScore("21", 20), { ok: false });
});

test("the standard scheme is fine, every broken rule is named like the API does", () => {
  assert.deepEqual(schemeProblems(STANDARD), []);
  assert.equal(schemeSum(STANDARD), 100);
  const short = [STANDARD[0], { ...STANDARD[1], weight: 30 }, STANDARD[2]];

  assert.deepEqual(schemeProblems(short), ["Сумма баллов 90 из 100: должно быть ровно 100"]);
  assert.deepEqual(schemeProblems([{ name: "ДЗ", weight: 100, kind: "manual" }]), [
    "Категория «посещаемость» (авто) должна быть ровно одна, сейчас 0",
  ]);
  assert.deepEqual(
    schemeProblems([
      { name: "П", weight: 50, kind: "attendance" },
      { name: "ДЗ", weight: 50, kind: "manual" },
      { name: "дз", weight: 0, kind: "manual" },
    ]),
    ["Категория «дз» повторяется", "«дз»: у категории, которую заполняет преподаватель, баллов от 1"],
  );
  assert.deepEqual(schemeProblems([]), ["Нет ни одной категории"]);
});

test("weights label, new names, moving and the removed categories", () => {
  assert.equal(weightsLabel(STANDARD), "Посещаемость 20 · Домашние задания 40 · Финал 40");
  assert.equal(newCategoryName(STANDARD), "Новая категория");
  assert.equal(newCategoryName([...STANDARD, { name: "Новая категория", weight: 0, kind: "manual" }]), "Новая категория 2");
  assert.deepEqual(move([1, 2, 3], 0, 1), [2, 1, 3]);
  assert.deepEqual(move([1, 2, 3], 0, -1), [1, 2, 3]);
  assert.deepEqual(removedCategories(STANDARD, [STANDARD[0], STANDARD[1]]).map((c) => c.key), ["final"]);
  assert.equal(parsePercent("85"), 85);
  assert.equal(parsePercent("101"), null);
  assert.equal(parsePercent(""), null);
});
