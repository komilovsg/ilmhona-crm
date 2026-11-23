/** Geometry of the room board: time on the vertical axis, one column per room inside each day. */

export const SLOT = 30; // minutes per printed row
export const TICK = 5; // minutes per grid line: a lesson may start at any 5 minutes
const DAY_FROM = 13 * 60;
const DAY_TO = 20 * 60;

export function minutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);

  return h * 60 + m;
}

export function clock(total: number): string {
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

type Timed = { start: string; end: string };

/** The hours the board shows: 13:00–20:00, widened to whole slots around earlier or later lessons. */
export function boardHours(lessons: Timed[]): { from: number; to: number } {
  let from = DAY_FROM;
  let to = DAY_TO;

  for (const l of lessons) {
    const start = minutes(l.start);
    // a lesson that runs past midnight ends with the day
    const end = minutes(l.end) > start ? minutes(l.end) : 24 * 60;

    from = Math.min(from, Math.floor(start / SLOT) * SLOT);
    to = Math.max(to, Math.ceil(end / SLOT) * SLOT);
  }

  return { from, to };
}

export function slotsOf(from: number, to: number): number[] {
  return Array.from({ length: (to - from) / SLOT }, (_, i) => from + i * SLOT);
}

/** First grid line and the number of lines a lesson takes (lines are TICK minutes, 1-based). */
export function linesOf(lesson: Timed, from: number): { line: number; span: number } {
  const start = minutes(lesson.start);
  const end = minutes(lesson.end) > start ? minutes(lesson.end) : 24 * 60;

  return {
    line: Math.round((start - from) / TICK) + 1,
    span: Math.max(1, Math.round((end - start) / TICK)),
  };
}

/** The same course is the same colour every week: the hue comes from its name. */
export function courseHue(name: string): number {
  let hash = 0;

  for (const ch of name.trim().toLowerCase()) hash = (hash * 31 + ch.codePointAt(0)!) % 3600;

  return (hash * 137) % 360;
}

/** A week without Sunday lessons is printed Monday to Saturday. */
export function boardDays(week: string[], lessons: { date: string }[]): string[] {
  return lessons.some((l) => l.date === week[6]) ? week : week.slice(0, 6);
}

export type Period = "week" | "month" | "half" | "year";

export const PERIODS: { key: Period; label: string }[] = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "half", label: "Полгода" },
  { key: "year", label: "Год" },
];

const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const MONTH_COUNT = { month: 1, half: 6, year: 12 } as const;

const iso = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);
const parts = (day: string) => day.split("-").map(Number) as [number, number, number];

export type MonthSpan = { from: string; to: string; title: string };

/** The months a period shows: the month of `day`, six months from it, or its calendar year. */
export function monthsOfPeriod(period: Exclude<Period, "week">, day: string): MonthSpan[] {
  const [y, m] = parts(day);
  const first = period === "year" ? 0 : m - 1;

  return Array.from({ length: MONTH_COUNT[period] }, (_, i) => {
    const start = new Date(Date.UTC(y, first + i, 1));
    const [yy, mm] = [start.getUTCFullYear(), start.getUTCMonth()];

    return { from: iso(yy, mm, 1), to: iso(yy, mm + 1, 0), title: `${MONTHS[mm]} ${yy}` };
  });
}

/** The days `from`..`to` in rows of one calendar week (Monday first); the edge weeks are short. */
export function weekBands(from: string, to: string): string[][] {
  const bands: string[][] = [];
  const [y, m, d] = parts(from);

  for (let i = 0; ; i++) {
    const date = new Date(Date.UTC(y, m - 1, d + i));
    const day = date.toISOString().slice(0, 10);

    if (day > to) break;
    if (i === 0 || date.getUTCDay() === 1) bands.push([]);
    bands[bands.length - 1].push(day);
  }

  return bands;
}

/** The day the board stands on after a step back (-1) or forward (1). */
export function shiftDay(period: Period, day: string, dir: -1 | 1): string {
  const [y, m, d] = parts(day);

  if (period === "week") return iso(y, m - 1, d + 7 * dir);
  if (period === "year") return iso(y + dir, 0, 1);

  return iso(y, m - 1 + MONTH_COUNT[period] * dir, 1);
}

export function periodTitle(period: Exclude<Period, "week">, day: string): string {
  const months = monthsOfPeriod(period, day);

  if (period === "year") return day.slice(0, 4);
  if (period === "month") return months[0].title;

  return `${months[0].title} – ${months[5].title}`;
}
