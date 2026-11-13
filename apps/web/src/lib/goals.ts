// Goals and notes: types and the small pure helpers the cards use (unit-tested).

export type AcademyGoal = {
  text: string;
  version: number;
  updated_at: string;
  updated_by: string | null;
};

export type GoalStatus = "достигнута" | "по графику" | "отстаём" | "срок прошёл";

export type Goal = {
  id: string;
  version: number;
  title: string;
  metric: string;
  metric_label: string;
  target: number;
  current: number;
  start_date: string;
  deadline: string;
  branch_id: string | null;
  branch_name: string | null;
  archived: boolean;
  notes_count: number;
  progress_pct: number;
  expected_pct: number;
  on_pace: boolean;
  status: GoalStatus;
};

export type Note = {
  id: string;
  version: number;
  text: string;
  goal_id: string | null;
  goal_title: string | null;
  course_id: string | null;
  course_name: string | null;
  cohort_id: string | null;
  cohort_code: string | null;
  created_at: string;
  updated_at: string;
};

export const GOAL_TEXT_MAX = 280;
export const NOTE_TEXT_MAX = 2000;
export const GOAL_TITLE_MAX = 120;

/** metric code -> label for the select, one line of explanation, and the unit after the numbers. */
export const METRICS: { key: string; label: string; hint: string; unit: string }[] = [
  { key: "graduates_total", label: "Выпускники", hint: "Студенты со статусом «выпускник», чей поток закончился в период цели.", unit: "" },
  { key: "active_students", label: "Активные студенты", hint: "Сколько студентов учатся сейчас (на сегодняшний день).", unit: "" },
  { key: "collection_rate_month", label: "Сбор оплат за месяц", hint: "Какой % ожидаемых оплат этого месяца уже подтверждён. План — в процентах.", unit: "%" },
  { key: "income", label: "Доход", hint: "Подтверждённые оплаты студентов за период цели, в TJS.", unit: "TJS" },
  { key: "new_enrollments", label: "Новые зачисления", hint: "Сколько зачислений в потоки сделано за период цели.", unit: "" },
  { key: "courses_launched", label: "Запуски курсов", hint: "Курсы, у которых первый поток начался в период цели.", unit: "" },
];

export function metricOf(key: string) {
  return METRICS.find((m) => m.key === key) ?? METRICS[0];
}

export type Tone = "success" | "primary" | "warning" | "danger";

/** Status colour; the chip always carries the status word too, never colour alone. */
export function statusTone(status: string): Tone {
  if (status === "достигнута") return "success";
  if (status === "по графику") return "primary";
  if (status === "отстаём") return "warning";

  return "danger";
}

const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });

export function formatNumber(n: number): string {
  return number.format(n);
}

/** «412 из 1 000», «850 из 1 000 TJS», «72 из 90 %». */
export function progressText(current: number, target: number, metric: string): string {
  const unit = metricOf(metric).unit;

  return `${formatNumber(current)} из ${formatNumber(target)}${unit ? ` ${unit}` : ""}`;
}

/** Characters left of a limit (negative never shown: the input is capped). */
export function charsLeft(text: string, max: number): number {
  return Math.max(0, max - text.length);
}

/** A target that is a positive number (comma or dot); `max` for a % metric. */
export function validTarget(text: string, metric: string): boolean {
  const n = Number(text.replace(",", ".").replace(/\s/g, ""));

  if (!Number.isFinite(n) || n <= 0) return false;

  return metric === "collection_rate_month" ? n <= 100 : true;
}

/** Ctrl/Cmd + Enter saves a note. */
export function isSaveShortcut(e: { key: string; ctrlKey: boolean; metaKey: boolean }): boolean {
  return e.key === "Enter" && (e.ctrlKey || e.metaKey);
}
