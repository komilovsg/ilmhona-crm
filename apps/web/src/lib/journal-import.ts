// Types and display helpers of the journal import (no React, no imports: unit-tested with node --test).
// What an import does is decided by the API; this file only words it.

export type ImportCounts = {
  add: number;
  same: number;
  differ: number;
  skip_future: number;
  skip_before_enrollment: number;
  skip_expelled: number;
  skip_no_lesson: number;
  unknown: number;
  lessons_to_create: number;
  matched: number;
  unmatched: number;
  missing: number;
};

export type ImportDate = {
  col: number;
  date: string;
  status: "lesson" | "create" | "future" | "no_lesson" | "cancelled" | "duplicate" | "outside" | "conflict";
  lesson_id: string | null;
  reason: string | null;
};

export type JournalPreview = {
  cohort: { id: string; code: string };
  file: { format: string; sheet: string; sheets: string[] };
  detected: { sheet: string; row: number; col: number; explicit: boolean };
  options: { create_lessons: boolean; overwrite: boolean };
  dates: ImportDate[];
  rows: { line: number; name: string; student_name: string; struck: boolean; tier: string; status: string }[];
  unmatched: { line: number; name: string; struck: boolean; marks: number; candidates: string[] }[];
  missing: { enrollment_id: string; student_name: string; status: string }[];
  unknown: { line: number; date: string; name: string; mark: string }[];
  counts: ImportCounts;
  differ: { line: number; date: string; student_name: string; mark: string; current: string | null }[];
};

export type JournalResult = { marks_added: number; marks_overwritten: number; lessons_created: number };

const DATE_STATUS: Record<ImportDate["status"], string> = {
  lesson: "урок есть",
  create: "урок будет добавлен",
  future: "ещё впереди, пропускаем",
  no_lesson: "урока нет",
  cancelled: "урок отменён",
  duplicate: "дата повторяется",
  outside: "вне дат потока",
  conflict: "аудитория занята",
};

export function dateStatusLabel(d: ImportDate): string {
  return d.status === "conflict" || d.status === "no_lesson" ? (d.reason ?? DATE_STATUS[d.status]) : DATE_STATUS[d.status];
}

/** How many marks the «Загрузить» button writes: new ones, plus the differing ones when overwriting. */
export function marksToWrite(counts: ImportCounts, overwrite: boolean): number {
  return counts.add + (overwrite ? counts.differ : 0);
}

/** The cells that will not be written, as «будущие даты: 3» chips (only the non-zero ones). */
export function skippedChips(c: ImportCounts): string[] {
  const rows: [number, string][] = [
    [c.skip_future, "будущие даты"],
    [c.skip_before_enrollment, "до зачисления"],
    [c.skip_expelled, "отчисленные"],
    [c.skip_no_lesson, "нет урока"],
    [c.unknown, "непонятные отметки"],
  ];

  return rows.filter(([n]) => n > 0).map(([n, label]) => `${label}: ${n}`);
}

/** «Загружено отметок: 12, уроков добавлено: 2». */
export function resultText(r: JournalResult): string {
  const parts = [`Загружено отметок: ${r.marks_added + r.marks_overwritten}`];

  if (r.lessons_created > 0) parts.push(`уроков добавлено: ${r.lessons_created}`);

  return parts.join(", ");
}
