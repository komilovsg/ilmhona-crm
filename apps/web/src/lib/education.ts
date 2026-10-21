// Pure helpers of the education screens (no React, no imports: unit-tested with node --test).

export const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] as const; // ISO 1..7

export const COHORT_STATUSES = ["набор", "активный", "завершён", "отменён"] as const;
export const ENROLLMENT_STATUSES = ["активный", "завершил", "выпускник", "отчислен"] as const;
export const STUDENT_STATUSES = ["активный", "выпускник", "отчислен", "без зачисления"] as const;

export type Tone = "default" | "primary" | "secondary" | "success" | "warning" | "danger";

export function cohortTone(status: string): Tone {
  switch (status) {
    case "набор":
      return "warning";
    case "активный":
      return "success";
    case "отменён":
      return "danger";
    default:
      return "default";
  }
}

export function studentTone(status: string): Tone {
  switch (status) {
    case "активный":
      return "success";
    case "выпускник":
      return "primary";
    case "отчислен":
      return "danger";
    default:
      return "default";
  }
}

/** «Пн, Ср, Пт» from ISO weekday numbers (1 = Monday). */
export function daysLabel(days: number[]): string {
  return [...days]
    .sort((a, b) => a - b)
    .map((d) => WEEKDAYS[d - 1])
    .join(", ");
}

/** Fill of a cohort in percent, 0..100 (over-full shows as full). */
export function fillPercent(enrolled: number, capacity: number): number {
  if (capacity <= 0) return 0;

  return Math.max(0, Math.min(100, Math.round((enrolled / capacity) * 100)));
}

/** Dates travel as `YYYY-MM-DD` strings; math happens at noon UTC so DST never shifts a day. */
function toDate(iso: string): Date {
  return new Date(`${iso}T12:00:00Z`);
}

export function addDays(iso: string, days: number): string {
  const d = toDate(iso);

  d.setUTCDate(d.getUTCDate() + days);

  return d.toISOString().slice(0, 10);
}

/** ISO weekday 1..7 of a `YYYY-MM-DD` date. */
export function isoWeekday(iso: string): number {
  return toDate(iso).getUTCDay() || 7;
}

export function mondayOf(iso: string): string {
  return addDays(iso, 1 - isoWeekday(iso));
}

export function weekOf(iso: string): string[] {
  const monday = mondayOf(iso);

  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

/** Today in Asia/Dushanbe as `YYYY-MM-DD`, whatever the browser's zone is. */
export function todayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dushanbe" }).format(now);
}

/** «12.03» */
export function dayMonth(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

/** «12.03.2030» */
export function fullDate(iso: string): string {
  return `${dayMonth(iso)}.${iso.slice(0, 4)}`;
}

/** «Пн 12.03» */
export function dayTitle(iso: string): string {
  return `${WEEKDAYS[isoWeekday(iso) - 1]} ${dayMonth(iso)}`;
}

export function formatPrice(value: string | number): string {
  const n = Number(value);
  const fraction = Number.isInteger(n) ? 0 : 2; // «650 TJS», but «3 450,50 TJS»

  return `${new Intl.NumberFormat("ru-RU", { minimumFractionDigits: fraction, maximumFractionDigits: 2 }).format(n)} TJS`;
}

export const MIN_DATE = "2020-01-01";
export const MAX_DATE = "2035-12-31";

function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);

  return h * 60 + m;
}

/** Lesson window (#6): 07:00-22:00 and 30 minutes to 4 hours. */
export function timeProblem(startTime: string, endTime: string): string | null {
  if (!startTime || !endTime) return null;
  if (startTime < "07:00" || endTime > "22:00") return "Занятия идут с 07:00 до 22:00.";

  const length = minutes(endTime) - minutes(startTime);

  if (length < 30 || length > 240) return "Урок длится от 30 минут до 4 часов.";

  return null;
}

/** The rules the API enforces (SPEC; bugs #6 #8), so the form says what is wrong before saving. */
export function scheduleProblem(f: {
  start: string;
  end: string;
  startTime: string;
  endTime: string;
  weekdays: number[];
}): string | null {
  if (!f.start || !f.end || !f.startTime || !f.endTime) return null;
  if (f.start < MIN_DATE || f.end > MAX_DATE) return "Даты должны быть между 2020 и 2035 годом.";
  if (f.end <= f.start) return "Дата окончания должна быть позже даты начала.";
  const time = timeProblem(f.startTime, f.endTime);

  if (time) return time;
  if (f.weekdays.length === 0) return "Выберите хотя бы один день недели.";

  return null;
}
