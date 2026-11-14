import { CalendarDate, CalendarDateTime, type DateValue } from "@internationalized/date";

/** `YYYY-MM-DD` (or `YYYY-MM-DDTHH:mm` with `withTime`) as a picker value; null when empty or malformed. */
export function parseIso(value: string | null | undefined, withTime = false): DateValue | null {
  const m = (value ?? "").match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);

  if (!m) return null;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];

  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  if (withTime) return new CalendarDateTime(y, mo, d, Number(m[4] ?? 0), Number(m[5] ?? 0));

  return new CalendarDate(y, mo, d);
}

const pad = (n: number, w = 2) => String(n).padStart(w, "0");

/** A picker value back to the ISO string the pages keep; "" for none. */
export function toIso(v: { year: number; month: number; day: number; hour?: number; minute?: number } | null, withTime = false): string {
  if (!v) return "";
  const date = `${pad(v.year, 4)}-${pad(v.month)}-${pad(v.day)}`;

  return withTime ? `${date}T${pad(v.hour ?? 0)}:${pad(v.minute ?? 0)}` : date;
}
