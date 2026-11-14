// Role dashboards: API types and the small pure helpers the cards use (unit-tested, no React).

export type LayoutCard = { id: string; title: string; visible: boolean };
export type Layout = { cards: LayoutCard[]; is_default: boolean; version: number };

export type MonthHero = {
  month: string;
  collected: string;
  expected: string;
  collection_pct: number;
  debt: string | null;
  debtors: number | null;
  profit: string | null;
  income: string | null;
  income_prev: string | null;
  income_change_pct: number | null;
  new_students: number;
  new_students_prev: number;
  new_students_change: number;
};

export type Lane = {
  id: string;
  code: string;
  course_name: string;
  branch_name: string;
  status: string;
  start_date: string;
  end_date: string;
  enrolled: number;
  capacity: number;
  fill_pct: number;
  over_capacity: { enrolled: number; capacity: number } | null;
};
export type Timeline = { window_start: string; window_end: string; today: string; items: Lane[] };

export type AlertItem = { key: string; severity: "danger" | "warning" | "info"; title: string; hint: string; href: string };

export type DemandRow = { course_id: string; course_name: string; leads: number; previous: number; change_pct: number | null };
export type Demand = { since: string; until: string; items: DemandRow[]; no_course: number; total: number };

export type BranchMonths = { months: string[]; series: { branch_id: string; name: string; values: string[] }[] };

export type Tile =
  | { key: "callbacks"; count: number; overdue: number }
  | { key: "debtors"; count: number; sum: string }
  | { key: "pending"; count: number; sum: string }
  | { key: "new_leads"; count: number };

export type CallLead = {
  id: string;
  full_name: string;
  phone: string | null;
  status: string;
  course_name: string | null;
  next_contact_at: string | null;
};

export type SeatRow = {
  id: string;
  code: string;
  course_name: string;
  start_date: string;
  enrolled: number;
  capacity: number;
  free: number;
  fill_pct: number;
  over_capacity: { enrolled: number; capacity: number } | null;
};

export type Week = {
  since: string;
  until: string;
  leads: number | null;
  leads_change: number | null;
  enrolled: number;
  enrolled_change: number;
  payments_count: number | null;
  payments_sum: string | null;
  debt: string | null;
  debtors: number | null;
};

/** Russian plural: plural(2, "лид", "лида", "лидов") -> "лида". */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;

  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;

  return many;
}

export type Trend = { text: string; tone: "up" | "down" | "flat" | "new" };

/** «▲ 48 %» / «▼ 8 %» / «новое»: always text, the colour only repeats it. */
export function trendOf(pct: number | null): Trend {
  if (pct === null) return { text: "новое", tone: "new" };
  if (pct > 0) return { text: `▲ ${Math.round(pct)} %`, tone: "up" };
  if (pct < 0) return { text: `▼ ${Math.abs(Math.round(pct))} %`, tone: "down" };

  return { text: "0 %", tone: "flat" };
}

/** «+9» / «−3» / «0»: a signed change with a real minus. */
export function signed(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0";
}

const DAY = 86_400_000;

function utc(iso: string): number {
  return Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
}

export type Span = { left: number; width: number };

/** Where a cohort's bar sits on the timeline, in % of the window (clipped to it; end day included). */
export function laneSpan(start: string, end: string, winStart: string, winEnd: string): Span {
  const total = (utc(winEnd) - utc(winStart)) / DAY + 1;
  const from = Math.max(utc(start), utc(winStart));
  const to = Math.min(utc(end), utc(winEnd));
  const left = ((from - utc(winStart)) / DAY / total) * 100;
  const width = Math.max(((to - from) / DAY + 1) / total * 100, 1.5);

  return { left, width: Math.min(width, 100 - left) };
}

/** The «today» line, in % of the window. */
export function todayAt(today: string, winStart: string, winEnd: string): number {
  const total = (utc(winEnd) - utc(winStart)) / DAY + 1;

  return Math.min(Math.max(((utc(today) - utc(winStart)) / DAY / total) * 100, 0), 100);
}

const MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const MONTH_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const MONTH_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
const WEEKDAYS = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];

export const monthName = (iso: string) => MONTH_NAMES[Number(iso.slice(5, 7)) - 1] ?? "";
export const monthShort = (iso: string) => MONTH_SHORT[Number(iso.slice(5, 7)) - 1] ?? "";

/** «14 ноября» */
export function dayMonth(iso: string): string {
  return `${Number(iso.slice(8, 10))} ${MONTH_GEN[Number(iso.slice(5, 7)) - 1] ?? ""}`;
}

/** «пятница, 14 ноября» */
export function weekdayDate(iso: string): string {
  return `${WEEKDAYS[new Date(utc(iso)).getUTCDay()]}, ${dayMonth(iso)}`;
}

/** «20.11» */
export function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
}

export type Move = { id: string; delta: -1 | 1 };

/** The up/down buttons of the customise list: move one card by one place (no-op at the ends). */
export function moveCard<T extends { id: string }>(cards: T[], { id, delta }: Move): T[] {
  const from = cards.findIndex((c) => c.id === id);
  const to = from + delta;

  if (from < 0 || to < 0 || to >= cards.length) return cards;
  const next = [...cards];

  [next[from], next[to]] = [next[to], next[from]];

  return next;
}

/** Layout -> what the PUT sends: the order of all cards and the ids switched off. */
export function layoutBody(cards: LayoutCard[]): { order: string[]; hidden: string[] } {
  return { order: cards.map((c) => c.id), hidden: cards.filter((c) => !c.visible).map((c) => c.id) };
}

/** Phone number for wa.me: digits only. */
export function whatsappHref(phone: string): string {
  return `https://wa.me/${phone.replace(/\D/g, "")}`;
}
