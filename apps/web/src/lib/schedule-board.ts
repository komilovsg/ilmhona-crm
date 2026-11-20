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
