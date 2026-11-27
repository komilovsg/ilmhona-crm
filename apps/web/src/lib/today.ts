import type { LessonItem } from "./types";

export type LessonPhase = "past" | "now" | "next" | "later";

/** Minutes since midnight of «HH:MM». */
export function minutesOf(hm: string): number {
  const [h, m] = hm.split(":").map(Number);

  return h * 60 + m;
}

/** The wall clock in Dushanbe (the academy's time zone) as minutes since midnight. */
export function dushanbeMinutes(now: Date): number {
  const parts = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Dushanbe",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);

  return get("hour") * 60 + get("minute");
}

/**
 * Phase of each of today's lessons (time order): finished, in progress, the first one still to come
 * («next» — the focal one only when nothing is running), the rest «later».
 */
export function lessonPhases(lessons: LessonItem[], nowMin: number): LessonPhase[] {
  let nextTaken = false;

  return lessons.map((l) => {
    if (nowMin >= minutesOf(l.end)) return "past";
    if (nowMin >= minutesOf(l.start)) {
      nextTaken = true; // a running lesson is the focus; the rest just wait

      return "now";
    }
    if (!nextTaken) {
      nextTaken = true;

      return "next";
    }

    return "later";
  });
}

/** Monday of the week of `iso` (YYYY-MM-DD). */
export function weekStart(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const back = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - back);

  return d.toISOString().slice(0, 10);
}

/** Unmarked lessons split into this week and earlier (the list arrives oldest first). */
export function splitUnfilled(unfilled: LessonItem[], today: string): { week: LessonItem[]; earlier: LessonItem[] } {
  const monday = weekStart(today);

  return {
    week: unfilled.filter((l) => l.date >= monday),
    earlier: unfilled.filter((l) => l.date < monday),
  };
}

/** «завтра» / «через 3 дня» between two ISO dates. */
export function inDays(from: string, to: string): string {
  const n = Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
  if (n === 1) return "завтра";
  if (n === 2) return "послезавтра";
  const mod10 = n % 10;
  const mod100 = n % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "день" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "дня" : "дней";

  return `через ${n} ${word}`;
}
