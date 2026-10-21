// Pure helpers of the money screens (no React, no imports: unit-tested with node --test).

export const PAYMENT_METHODS = [
  { key: "alif", label: "Alif" },
  { key: "payvand", label: "Payvand" },
  { key: "наличные", label: "Наличные" },
] as const;

export const PAYMENT_STATUSES = ["ожидает", "подтверждено"] as const;

export function methodLabel(method: string): string {
  return PAYMENT_METHODS.find((m) => m.key === method)?.label ?? method;
}

export type Tone = "default" | "primary" | "secondary" | "success" | "warning" | "danger";

export function paymentTone(status: string): Tone {
  return status === "подтверждено" ? "success" : "warning";
}

/** Salary row state: выплачено / частично / к выплате / запланировано. */
export function salaryTone(state: string): Tone {
  switch (state) {
    case "выплачено":
      return "success";
    case "частично":
      return "warning";
    case "к выплате":
      return "danger";
    default:
      return "default";
  }
}

const MONTHS = [
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

/** «октябрь 2026» from `2026-10-01` or `2026-10`. */
export function monthLabel(iso: string): string {
  const month = Number(iso.slice(5, 7));

  return `${MONTHS[month - 1] ?? iso.slice(5, 7)} ${iso.slice(0, 4)}`;
}

/** `YYYY-MM` of a `YYYY-MM-DD` day. */
export function monthOf(day: string): string {
  return day.slice(0, 7);
}

/** `YYYY-MM` shifted by `delta` months. */
export function shiftMonth(month: string, delta: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + delta;

  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** Months around `current` for a filter: `back` before, `ahead` after, newest first. */
export function monthOptions(current: string, back = 12, ahead = 6): { key: string; label: string }[] {
  return Array.from({ length: back + ahead + 1 }, (_, i) => {
    const key = shiftMonth(current, ahead - i);

    return { key, label: monthLabel(key) };
  });
}

/** «1, 2 из 4» — which months of the course are paid. */
export function paidMonthsLabel(months: number[], total: number): string {
  return months.length ? `${months.join(", ")} из ${total}` : `0 из ${total}`;
}

/** What a person typed as an amount, ready to parse: «1 500,50» / «1500,5» -> «1500.50» / «1500.5». */
export function moneyInput(text: string): string {
  return text.replace(/[\s\u00a0\u202f]/g, "").replace(",", ".");
}

/** A normalised amount for the API and for the conflict comparison: «500.00» and 500 are one value. */
export function amountText(value: string | number): string {
  const text = moneyInput(String(value));
  const n = Number(text);

  return text !== "" && Number.isFinite(n) ? String(n) : "";
}

const MONEY_TEXT = /^\d{1,10}(\.\d{1,2})?$/;

export function validAmount(text: string): boolean {
  const t = moneyInput(text);

  return MONEY_TEXT.test(t) && Number(t) > 0;
}

/** A rate (or a budget) may be 0 (not set yet), never negative. */
export function validRate(text: string): boolean {
  return MONEY_TEXT.test(moneyInput(text));
}

export function newKey(): string {
  return globalThis.crypto.randomUUID();
}
