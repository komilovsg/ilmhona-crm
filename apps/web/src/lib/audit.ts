// Readable audit diffs (no React, no imports: unit-tested with node --test).

export type Names = Record<string, string>;
export type DiffLine = { label: string; before: string; after: string };

const FIELDS: Record<string, string> = {
  login: "Логин",
  full_name: "ФИО",
  phone: "Телефон",
  email: "Email",
  branch_id: "Филиал",
  role_id: "Роль",
  is_active: "Активен",
  name: "Название",
  expires_at: "Временный пароль до",
};

const LEVELS: Record<string, string> = { view: "Просмотр", change: "Изменение" };
const REFS = new Set(["branch_id", "role_id"]);
const NONE = "—";

function pair(change: unknown): [unknown, unknown] {
  return Array.isArray(change) && change.length === 2 ? [change[0], change[1]] : [undefined, change];
}

function plain(value: unknown): string {
  if (value === null || value === undefined) return NONE;
  if (typeof value === "boolean") return value ? "Да" : "Нет";

  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** `{field: [before, after]}` -> «Раздел: было → стало» lines, ids replaced by names. */
export function diffLines(diff: Record<string, unknown>, names: Names, sections: Names): DiffLine[] {
  const lines: DiffLine[] = [];

  for (const [field, change] of Object.entries(diff)) {
    if (field === "permissions" && change && typeof change === "object") {
      for (const [section, perm] of Object.entries(change as Record<string, unknown>)) {
        const [before, after] = pair(perm);
        const level = (v: unknown) => (typeof v === "string" ? (LEVELS[v] ?? v) : "Нет");

        lines.push({ label: sections[section] ?? section, before: level(before), after: level(after) });
      }
      continue;
    }

    const [before, after] = pair(change);
    const show = (v: unknown) => (REFS.has(field) && typeof v === "string" ? (names[v] ?? "удалён") : plain(v));

    lines.push({ label: FIELDS[field] ?? field, before: show(before), after: show(after) });
  }

  return lines;
}
