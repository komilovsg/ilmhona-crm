import assert from "node:assert/strict";
import { test } from "node:test";

import { diffLines } from "./audit.ts";

const names = { "r-1": "Менеджер", "b-1": "Душанбе" };
const sections = { leads: "Лиды", payments: "Оплаты" };

test("references show names, not ids; a missing one is «удалён»", () => {
  const lines = diffLines({ role_id: ["r-1", "r-gone"], branch_id: [null, "b-1"] }, names, sections);

  assert.deepEqual(lines, [
    { label: "Роль", before: "Менеджер", after: "удалён" },
    { label: "Филиал", before: "—", after: "Душанбе" },
  ]);
});

test("permission diffs read «Раздел: было → стало»", () => {
  const lines = diffLines({ permissions: { leads: [null, "view"], payments: ["change", null] } }, names, sections);

  assert.deepEqual(lines, [
    { label: "Лиды", before: "Нет", after: "Просмотр" },
    { label: "Оплаты", before: "Изменение", after: "Нет" },
  ]);
});

test("plain fields: labels, booleans, null", () => {
  assert.deepEqual(diffLines({ is_active: [true, false], phone: [null, "+992"] }, names, sections), [
    { label: "Активен", before: "Да", after: "Нет" },
    { label: "Телефон", before: "—", after: "+992" },
  ]);
});
