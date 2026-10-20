// Edit conflicts (#25), the pure part (no React: unit-tested with node --test).
// A form holds `values` (its fields), the API record it loaded (`base`) and its version. A 409
// `stale_version` brings the record as it is now (`current`) and who changed it last.

export type Values = Record<string, unknown>;

export type StaleInfo<R> = {
  current: R;
  version: number;
  changedBy: string | null;
  changedAt: string | null;
};

type ErrorLike = { status?: number; code?: string; params?: Record<string, unknown> };

/** The 409 `stale_version` problem of an `api()` call, or null for any other error. */
export function staleOf<R>(error: unknown): StaleInfo<R> | null {
  const e = error as ErrorLike | null;

  if (!e || e.code !== "stale_version" || !e.params?.current) return null;

  return {
    current: e.params.current as R,
    version: Number(e.params.version),
    changedBy: (e.params.changed_by as string | undefined) ?? null,
    changedAt: (e.params.changed_at as string | undefined) ?? null,
  };
}

export function same(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/** The fields the user changed against the record they loaded: the PATCH body (only these go out). */
export function changedKeys<V extends Values>(base: V, values: V): (keyof V)[] {
  return (Object.keys(values) as (keyof V)[]).filter((k) => !same(base[k], values[k]));
}

/**
 * The user's edit on top of a fresher record: a field the user changed keeps their value, every
 * other field takes the new record's. Two people editing different fields both survive.
 */
export function rebase<V extends Values>(oldBase: V, newBase: V, mine: V): V {
  const mineChanged = new Set(changedKeys(oldBase, mine));

  return Object.fromEntries(
    (Object.keys(mine) as (keyof V)[]).map((k) => [k, mineChanged.has(k) ? mine[k] : newBase[k]]),
  ) as V;
}

export type ConflictLine = { label: string; mine: string; theirs: string };

const NONE = "—";

export function plain(value: unknown): string {
  if (value === null || value === undefined || value === "") return NONE;
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (Array.isArray(value)) return value.length ? value.join(", ") : NONE;

  return String(value);
}

/** «Ваши изменения» / «Сейчас в базе» lines for the fields the user changed. */
export function conflictLines<V extends Values>(
  keys: (keyof V)[],
  mine: V,
  theirs: V,
  labels: Partial<Record<keyof V, string>>,
  show: Partial<Record<keyof V, (value: never) => string>> = {},
): ConflictLine[] {
  const text = (k: keyof V, v: unknown) => (show[k] ? (show[k] as (value: unknown) => string)(v) : plain(v));

  return keys.map((k) => ({
    label: labels[k] ?? String(k),
    mine: text(k, mine[k]),
    theirs: text(k, theirs[k]),
  }));
}

const clock = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Asia/Dushanbe",
  hour: "2-digit",
  minute: "2-digit",
});

/** «Запись изменил Курбон в 14:05». */
export function whoWhen(info: { changedBy: string | null; changedAt: string | null }): string {
  const who = info.changedBy ?? "другой пользователь";
  const at = info.changedAt ? ` в ${clock.format(new Date(info.changedAt))}` : "";

  return `Запись изменил ${who}${at}.`;
}
