import type { CohortRow } from "./types.ts";

const OPEN = ["набор", "активный"];

/** Cohorts that still take students: «набор» or «активный» and not full. */
export function openCohorts(cohorts: CohortRow[]): CohortRow[] {
  return cohorts.filter((c) => OPEN.includes(c.status) && c.fill.enrolled < c.capacity);
}

/**
 * The convert dialog's list: cohorts of the lead's course first (`match`), the rest after.
 * `auto` is the cohort to preselect: only when exactly one open cohort fits the lead's course.
 */
export function convertCohorts(cohorts: CohortRow[], courseId: string | null) {
  const open = openCohorts(cohorts);
  const isMatch = (c: CohortRow) => !!courseId && c.course_id === courseId;
  const matching = open.filter(isMatch);

  return {
    items: [...matching, ...open.filter((c) => !isMatch(c))],
    match: new Set(matching.map((c) => c.id)),
    auto: matching.length === 1 ? matching[0].id : null,
  };
}
