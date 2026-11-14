import type { CohortRow } from "./types.ts";

const OPEN = ["набор", "активный"];

/** Cohorts that still take students: «набор» or «активный». Full ones stay (capacity is soft), after the rest. */
export function openCohorts(cohorts: CohortRow[]): CohortRow[] {
  const open = cohorts.filter((c) => OPEN.includes(c.status));
  const over = (c: CohortRow) => c.fill.enrolled >= c.capacity;

  return [...open.filter((c) => !over(c)), ...open.filter(over)];
}

/**
 * The convert dialog's list: cohorts of the lead's course first (`match`), the rest after; inside each
 * group full cohorts come last. `auto` is the cohort to preselect: only when exactly one non-full open
 * cohort fits the lead's course.
 */
export function convertCohorts(cohorts: CohortRow[], courseId: string | null) {
  const open = openCohorts(cohorts);
  const isMatch = (c: CohortRow) => !!courseId && c.course_id === courseId;
  const matching = open.filter(isMatch);
  const roomy = matching.filter((c) => c.fill.enrolled < c.capacity);

  return {
    items: [...matching, ...open.filter((c) => !isMatch(c))],
    match: new Set(matching.map((c) => c.id)),
    auto: roomy.length === 1 && matching.length === 1 ? roomy[0].id : null,
  };
}
