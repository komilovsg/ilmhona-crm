// Pure helpers of the attendance screens (no React, no imports: unit-tested with node --test).
// The numbers themselves (percent, score, total) come from the API; this file only formats them
// and answers display questions.

export const GRADE_MAX = 40;
export const PASS_TOTAL = 70;

/** «56 %» or «—» while no lesson has been held. */
export function percentLabel(percent: number | null): string {
  return percent === null ? "—" : `${String(percent).replace(".", ",")} %`;
}

/** «отмечено 12/14» or «не отмечено». */
export function markedLabel(marked: number, total: number): string {
  if (total === 0) return "нет студентов";

  return marked === 0 ? "не отмечено" : `отмечено ${marked}/${total}`;
}

export type MarkState = "none" | "partial" | "done";

export function markState(marked: number, total: number): MarkState {
  if (marked === 0) return "none";

  return marked >= total ? "done" : "partial";
}

/** A grade input: «» clears, 0..40 whole numbers are valid, everything else is not. */
export function parseGrade(text: string): { ok: true; value: number | null } | { ok: false } {
  const t = text.trim();

  if (t === "") return { ok: true, value: null };
  if (!/^\d{1,2}$/.test(t)) return { ok: false };
  const n = Number(t);

  return n <= GRADE_MAX ? { ok: true, value: n } : { ok: false };
}

/** «3 урока». */
export function lessonsWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;

  if (mod10 === 1 && mod100 !== 11) return `${n} урок`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} урока`;

  return `${n} уроков`;
}

type ProgressGrid = {
  lessons: { id: string; date: string }[];
  students: { enrolled_at: string; marks: Record<string, unknown> }[];
};

/**
 * marked / total per lesson column of the grid (the phone list). A student counts for a lesson
 * from the day they were enrolled, like on the API side: `dushanbeDate` turns the ISO instant
 * `enrolled_at` into its calendar date in Asia/Dushanbe.
 */
export function lessonProgress(
  grid: ProgressGrid,
  dushanbeDate: (iso: string) => string,
): Record<string, { marked: number; total: number }> {
  const since = grid.students.map((s) => dushanbeDate(s.enrolled_at));

  return Object.fromEntries(
    grid.lessons.map((l) => {
      let total = 0;
      let marked = 0;

      grid.students.forEach((s, i) => {
        if (since[i] > l.date) return;
        total += 1;
        if (s.marks[l.id] !== undefined) marked += 1;
      });

      return [l.id, { marked, total }];
    }),
  );
}
