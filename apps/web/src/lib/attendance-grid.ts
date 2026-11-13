// Pure helpers of the journal table (month filter, mark keys). No React, no imports: unit-tested
// with node --test. Percentages stay on the API side.

export const ALL_MONTHS = "all";

type Lesson = { date: string; cancelled: boolean; held: boolean };

const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];

/** The months («2026-09») that have lessons, ascending. */
export function monthsOf(lessons: { date: string }[]): string[] {
  return [...new Set(lessons.map((l) => l.date.slice(0, 7)))].sort();
}

/** «Сен 2026» */
export function monthLabel(month: string): string {
  return `${MONTHS[Number(month.slice(5, 7)) - 1]} ${month.slice(0, 4)}`;
}

/** Today's month if it has lessons, else the latest month with held lessons, else «all». */
export function defaultMonth(lessons: Lesson[], today: string): string {
  const months = monthsOf(lessons);
  const current = today.slice(0, 7);

  if (months.includes(current)) return current;
  const held = monthsOf(lessons.filter((l) => l.held));

  return held.length ? held[held.length - 1] : ALL_MONTHS;
}

export function lessonsOfMonth<T extends { date: string }>(lessons: T[], month: string): T[] {
  return month === ALL_MONTHS ? lessons : lessons.filter((l) => l.date.startsWith(month));
}

/** Shortcut on a focused cell: 1 = был, 2 = не был; any other key is not a mark. */
export function keyMark(key: string): boolean | undefined {
  return key === "1" ? true : key === "2" ? false : undefined;
}

/** Arrow key -> [row, column] step between cells; undefined for other keys. */
export function arrowStep(key: string): [number, number] | undefined {
  const steps: Record<string, [number, number]> = {
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
  };

  return Object.hasOwn(steps, key) ? steps[key] : undefined;
}

/** A cell is a button when the lesson takes marks and the student was enrolled by its date. */
export function cellMarkable(lesson: { date: string; writable: boolean }, student: { enrolled_on: string }): boolean {
  return lesson.writable && student.enrolled_on <= lesson.date;
}

export type Mark = { present: boolean; reason: string | null };

/** The marks of a student with one cell set (`undefined` removes it: rollback of a first mark). */
export function withMark(marks: Record<string, Mark>, lessonId: string, mark: Mark | undefined): Record<string, Mark> {
  const { [lessonId]: _old, ...rest } = marks;

  return mark ? { ...rest, [lessonId]: mark } : rest;
}

export function markLabel(present: boolean | undefined): string {
  return present === undefined ? "не отмечено" : present ? "присутствовал" : "отсутствовал";
}
