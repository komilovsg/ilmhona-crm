// Grading schemes, the pure part (no React, no imports: unit-tested with node --test).
// The numbers (points, totals, projected, pass) come from the API; this file checks a scheme the
// user is editing with the same rules as the API (so «Сумма: 90 из 100» shows before saving),
// formats it and parses score inputs.

export type CategoryKind = "attendance" | "manual";

export type Category = { key?: string; name: string; weight: number; kind: CategoryKind };

export type SchemeFields = {
  categories: Category[];
  pass_score: number;
  target_retention: number;
  target_attendance: number;
  target_pass_rate: number;
};

export const TOTAL = 100;
export const MAX_CATEGORIES = 12;
export const NAME_MAX = 60;

export const TARGETS: { key: keyof Omit<SchemeFields, "categories">; label: string; hint: string }[] = [
  { key: "pass_score", label: "Проходной балл", hint: "От этого итога студент становится выпускником" },
  { key: "target_retention", label: "Удержание, %", hint: "Цель: доля студентов, дошедших до конца" },
  { key: "target_attendance", label: "Посещаемость, %", hint: "Цель: средняя посещаемость потока" },
  { key: "target_pass_rate", label: "Проходные, %", hint: "Цель: доля студентов с проходным баллом" },
];

export const KIND_LABEL: Record<CategoryKind, string> = { attendance: "авто", manual: "вручную" };

export function schemeSum(categories: { weight: number }[]): number {
  return categories.reduce((s, c) => s + (Number.isFinite(c.weight) ? c.weight : 0), 0);
}

/** What is wrong with the categories, in Russian (the API's own wording); empty = fine. */
export function schemeProblems(categories: Category[]): string[] {
  const out: string[] = [];

  if (categories.length === 0) return ["Нет ни одной категории"];
  if (categories.length > MAX_CATEGORIES) out.push(`Категорий ${categories.length}, можно не больше ${MAX_CATEGORIES}`);
  const seen = new Set<string>();

  for (const c of categories) {
    const name = c.name.trim();

    if (!name) out.push("У категории нет названия");
    else if (name.length > NAME_MAX) out.push(`«${name.slice(0, 20)}…»: название длиннее ${NAME_MAX} символов`);
    const low = name.toLowerCase();

    if (name && seen.has(low)) out.push(`Категория «${name}» повторяется`);
    seen.add(low);
    if (!Number.isInteger(c.weight) || c.weight < 0 || c.weight > TOTAL) out.push(`«${name}»: баллы от 0 до ${TOTAL}`);
    else if (c.kind === "manual" && c.weight < 1)
      out.push(`«${name}»: у категории, которую заполняет преподаватель, баллов от 1`);
  }
  const att = categories.filter((c) => c.kind === "attendance").length;

  if (att !== 1) out.push(`Категория «посещаемость» (авто) должна быть ровно одна, сейчас ${att}`);
  const sum = schemeSum(categories);

  if (sum !== TOTAL) out.push(`Сумма баллов ${sum} из ${TOTAL}: должно быть ровно ${TOTAL}`);

  return out;
}

/** «Посещаемость 20 · Домашние задания 40 · Финал 40». */
export function weightsLabel(categories: Category[]): string {
  return categories.map((c) => `${c.name} ${c.weight}`).join(" · ");
}

/** A whole number input 0..100 («» = not a number yet). */
export function parsePercent(text: string): number | null {
  const t = text.trim();

  if (!/^\d{1,3}$/.test(t)) return null;
  const n = Number(t);

  return n <= TOTAL ? n : null;
}

/** A score input: «» clears, 0..max whole numbers are valid, everything else is not. */
export function parseScore(text: string, max: number): { ok: true; value: number | null } | { ok: false } {
  const t = text.trim();

  if (t === "") return { ok: true, value: null };
  if (!/^\d{1,3}$/.test(t)) return { ok: false };
  const n = Number(t);

  return n <= max ? { ok: true, value: n } : { ok: false };
}

/** The new manual category added by «Добавить категорию»: a free name, 0 points to fill in. */
export function newCategoryName(categories: Category[]): string {
  const names = new Set(categories.map((c) => c.name.trim().toLowerCase()));

  for (let i = 1; ; i += 1) {
    const name = i === 1 ? "Новая категория" : `Новая категория ${i}`;

    if (!names.has(name.toLowerCase())) return name;
  }
}

/** Move a category one place up (-1) or down (+1). */
export function move<T>(list: T[], index: number, by: -1 | 1): T[] {
  const to = index + by;

  if (to < 0 || to >= list.length) return list;
  const next = [...list];

  [next[index], next[to]] = [next[to], next[index]];

  return next;
}

/** The removed manual categories (by key) between the saved scheme and the edited one. */
export function removedCategories(before: Category[], after: Category[]): Category[] {
  const kept = new Set(after.map((c) => c.key).filter(Boolean));

  return before.filter((c) => c.kind === "manual" && c.key && !kept.has(c.key));
}
