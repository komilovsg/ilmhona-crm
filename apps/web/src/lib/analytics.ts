// Types and display helpers of the cohort «Аналитика» tab. Every number comes from the API
// (`app/metrics/cohort_analytics.py`); this file only names and formats them.

export type Period = "week" | "month" | "course";
export type Status = "ok" | "below" | null;

export type Reason = { code: string; text: string };

export type RiskRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  /** absent when the user may not see the cohort's students */
  phone?: string | null;
  level: "red" | "orange";
  reasons: Reason[];
  attendance_percent: number | null;
  projected: number | null;
};

export type TopRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  attendance_percent: number;
  projected: number;
};

export type WeekPoint = {
  week_start: string;
  week_end: string;
  lessons: number;
  present: number;
  marked: number;
  percent: number | null;
};

export type FinalRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  points: Record<string, number>;
  total: number;
  passed: boolean;
  excellent: boolean;
  attendance_percent: number | null;
};

export type CohortAnalytics = {
  cohort_id: string;
  cohort_code: string;
  period: Period;
  window: { from: string | null; to: string; offset: number };
  nav: { prev: boolean; next: boolean };
  scheme: { source: "standard" | "cohort"; pass_score: number; target_retention: number; target_attendance: number; target_pass_rate: number };
  thresholds: { top_attendance: number; top_projected: number };
  retention: {
    started: number;
    now: number;
    left: { expelled: number; stopped: number };
    late_joined: number;
    percent: number | null;
    target: number;
    status: Status;
  };
  attendance: {
    weeks: WeekPoint[];
    lessons: number;
    present: number;
    marked: number;
    percent: number | null;
    target: number;
    status: Status;
  };
  grades: {
    buckets: { label: string; from: number; to: number; count: number }[];
    students: number;
    no_data: number;
    average: number | null;
    pass_score: number;
    pass_rate: { passed: number; of: number; percent: number | null; target: number; status: Status };
  };
  risk: RiskRow[];
  top: TopRow[];
  final: {
    available: boolean;
    categories: { key: string; name: string; weight: number; kind: string }[];
    pass_score: number;
    rows: FinalRow[];
  };
};

export const PERIODS: { key: Period; label: string }[] = [
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "course", label: "Весь курс" },
];

const MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"];
const MONTHS_OF = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];

const parts = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);

  return { y, m: m - 1, d };
};

/** «10–16 ноября» / «30 ноября – 6 декабря» for a week, «Ноябрь 2026» for a month, «Весь курс». */
export function periodLabel(period: Period, from: string | null, to: string): string {
  if (period === "course" || !from) return "Весь курс";
  const a = parts(from);
  const b = parts(to);

  if (period === "month") return `${MONTHS[a.m][0].toUpperCase()}${MONTHS[a.m].slice(1)} ${a.y}`;

  return a.m === b.m ? `${a.d}–${b.d} ${MONTHS_OF[b.m]}` : `${a.d} ${MONTHS_OF[a.m]} – ${b.d} ${MONTHS_OF[b.m]}`;
}

/** The text that always goes with a status colour. */
export function statusLabel(status: Status): string {
  if (status === "ok") return "в норме";
  if (status === "below") return "ниже цели";

  return "нет данных";
}

/** «10.11» of `2026-11-10`. */
export function dayMonth(iso: string): string {
  const [, m, d] = iso.split("-");

  return `${d}.${m}`;
}

/** «10.11–16.11». */
export function weekRange(w: { week_start: string; week_end: string }): string {
  return `${dayMonth(w.week_start)}–${dayMonth(w.week_end)}`;
}

/** «66,7 %» or «—». */
export function pct(n: number | null): string {
  return n === null ? "—" : `${String(n).replace(".", ",")} %`;
}

/** «Начали 20 → сейчас 17 · 85 %». */
export function retentionLine(r: CohortAnalytics["retention"]): string {
  const late = r.late_joined > 0 ? ` · присоединились позже: ${r.late_joined}` : "";

  return `Начали ${r.started} → сейчас ${r.now} · ${pct(r.percent)}${late}`;
}

/** «ушли: отчислено 2, перестали ходить 1» or null when nobody left. */
export function leftLine(left: { expelled: number; stopped: number }): string | null {
  const parts = [left.expelled && `отчислено ${left.expelled}`, left.stopped && `перестали ходить ${left.stopped}`].filter(Boolean);

  return parts.length ? `ушли: ${parts.join(", ")}` : null;
}

/** Position (0..1 from the bottom) of a percent on the 0–100 axis. */
export function share(percent: number): number {
  return Math.min(1, Math.max(0, percent / 100));
}
