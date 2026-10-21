// The month of a payment: is it paid, who paid it, who is paying it right now (pure, no imports:
// unit-tested with node --test). The API rule: a month takes payments (pending + confirmed) up to
// the cohort's price; `GET /payments/month` tells the form what is entered and who holds the month.

type Money = string | number;

export type MonthPayment = {
  id: string;
  amount: Money;
  method: string;
  paid_at: string;
  status: string;
  created_by: string | null;
  created_at: string;
};

/** `GET /payments/month` (and `POST /payments/month/hold`, plus `acquired`). */
export type MonthStatus = {
  enrollment_id: string;
  month_no: number;
  price: Money;
  paid: Money;
  remaining: Money;
  /** Above the price (old-system data, no cap then); remaining is 0 then, never negative. */
  overpaid?: Money;
  full: boolean;
  payments: MonthPayment[];
  held_by: { id: string; name: string } | null;
  until: string | null;
  mine: boolean;
  acquired?: boolean;
};

/** One month of an enrollment as the money endpoints give it (`month_states`). */
export type MonthState = {
  month_no: number;
  paid: Money;
  pending: Money;
  price: Money;
  remaining: Money;
  overpaid?: Money;
  state: "не оплачен" | "частично" | "оплачен";
};

/** First month that still takes a payment; null when every month is full. */
export function defaultMonth(months: number, fullMonths: number[]): number | null {
  for (let m = 1; m <= months; m++) if (!fullMonths.includes(m)) return m;

  return null;
}

/** The next month after `month` that still takes a payment (else the first one before it). */
export function nextOpenMonth(months: number, fullMonths: number[], month: number): number | null {
  const full = [...fullMonths, month];

  for (let m = month + 1; m <= months; m++) if (!full.includes(m)) return m;

  return defaultMonth(months, full);
}

/** «700 TJS», «3 450,50 TJS». */
export function tjs(value: Money): string {
  const n = Number(value);
  const fraction = Number.isInteger(n) ? 0 : 2;

  return `${new Intl.NumberFormat("ru-RU", { minimumFractionDigits: fraction, maximumFractionDigits: 2 }).format(n)} TJS`.replace(
    /[  ]/g,
    " ",
  );
}

const WHEN = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Asia/Dushanbe",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** «21.10 в 13:39» (Asia/Dushanbe). */
export function whenText(iso: string): string {
  const parts = Object.fromEntries(WHEN.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));

  return `${parts.day}.${parts.month} в ${parts.hour}:${parts.minute}`;
}

export function statusText(status: string): string {
  return status === "ожидает" ? "ожидает подтверждения" : status;
}

function who(p: MonthPayment): string {
  return `${p.created_by ?? "импорт"}, ${whenText(p.created_at)} (${statusText(p.status)})`;
}

/** «700 TJS — Курбонзода К., 21.10 в 13:39 (ожидает подтверждения)»; several payments: each one. */
export function paymentsText(paid: Money, payments: MonthPayment[]): string {
  if (payments.length === 1) return `${tjs(paid)} — ${who(payments[0])}`;

  return `${tjs(paid)}${payments.length ? ` (${payments.map((p) => `${tjs(p.amount)} — ${who(p)}`).join("; ")})` : ""}`;
}

/** «Месяц 2 уже оплачен: 700 TJS — Курбонзода К., 21.10 в 13:39 (ожидает подтверждения)». */
export function paidText(s: { month_no: number; paid: Money; overpaid?: Money; payments: MonthPayment[] }): string {
  const over = Number(s.overpaid ?? 0) > 0 ? ` (переплата ${tjs(s.overpaid ?? 0)})` : "";

  return `Месяц ${s.month_no} уже оплачен${over}: ${paymentsText(s.paid, s.payments)}`;
}

export function holdText(name: string, month: number): string {
  return `${name} сейчас вносит оплату за месяц ${month}`;
}

/** The text of a 409 of the month rule (null for any other error). */
export function monthConflictText(error: unknown): string | null {
  const e = error as { code?: string; params?: Record<string, unknown> } | null;
  const p = e?.params as { month_no: number; paid: Money; remaining: Money; payments: MonthPayment[] } | undefined;

  if (!e || !p) return null;
  if (e.code === "month_already_paid") return paidText(p);
  if (e.code === "month_overpaid")
    return `За месяц ${p.month_no} осталось оплатить ${tjs(p.remaining)}. Уже внесено: ${paymentsText(p.paid, p.payments)}`;

  return null;
}

/** «не оплачен» · «частично: 200 из 500 TJS» · «оплачен» · «переплата 200 TJS». */
export function monthStateLabel(s: Pick<MonthState, "state" | "paid" | "price" | "overpaid">): string {
  if (Number(s.overpaid ?? 0) > 0) return `переплата ${tjs(s.overpaid ?? 0)}`;
  if (s.state === "частично") return `частично: ${tjs(s.paid).replace(" TJS", "")} из ${tjs(s.price)}`;

  return s.state;
}

/**
 * «1 из 4» — months оплачен by the same definition as the cap (pending + confirmed ≥ price);
 * «(1 ожидает подтверждения)» when some of them are covered by pending payments.
 */
export function paidCountLabel(states: Pick<MonthState, "state" | "pending">[], months: number): string {
  const paid = states.filter((s) => s.state === "оплачен");
  const waiting = paid.filter((s) => Number(s.pending) > 0).length;

  return `${paid.length} из ${months}${waiting ? ` (${waiting} ожидает подтверждения)` : ""}`;
}

/** The month picker's label: «2-й», «2-й · оплачен», «2-й · частично: 200 из 500 TJS · ожидает». */
export function monthOptionLabel(
  month: number,
  state: Pick<MonthState, "state" | "paid" | "price" | "pending" | "overpaid"> | undefined,
): string {
  if (!state || state.state === "не оплачен") return `${month}-й`;

  // short enough for a 390 px phone: «3-й · 50,50 / 350 · ожидает»
  const text =
    state.state === "частично" && !(Number(state.overpaid ?? 0) > 0)
      ? `${tjs(state.paid).replace(" TJS", "")} / ${tjs(state.price).replace(" TJS", "")}`
      : monthStateLabel(state);

  return `${month}-й · ${text}${Number(state.pending) > 0 ? " · ожидает" : ""}`;
}

/** Amount of a partial payment: more than 0 and not more than what the month still needs. */
export function partialAmountOk(amount: string, remaining: Money): boolean {
  const n = Number(amount);

  return amount.trim() !== "" && Number.isFinite(n) && n > 0 && n <= Number(remaining);
}

/** «2: 300 TJS, 3: 500 TJS» — what is left of each started month (debtors). */
export function dueText(due: { month_no: number; remaining: Money }[]): string {
  return due.map((d) => `${d.month_no}: ${tjs(d.remaining)}`).join(", ");
}
